"""Reproducible, resumable search for a passing human contingency roster."""
from copy import deepcopy
import json
from pathlib import Path
from bisect import bisect_left
from itertools import islice
from time import perf_counter

from amr_contingency_inputs import validate_settings, shift_candidates, peak_people, roster_within_limits
from amr_contingency_runtime import simulate_candidate, StudyCancelled
from amr_project_runs import read_json
from amr_project import atomic_write
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
    # Serialization completes synchronously before the atomic replacement.
    # Do not recursively copy tens of thousands of task/stop records merely to
    # add a top-level hash; compact JSON retains the exact same evidence.
    value = dict(state)
    value.pop('evidence_sha256', None)
    value['evidence_sha256'] = config_hash(value)
    atomic_write(Path(path), json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',', ':')).encode('utf-8'))


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


def coverage_scores(candidates, unmet):
    """Exact interval overlap counts, including already-late deferred tasks.

    Sweep release times and count inserted deadlines with a Fenwick tree. This
    preserves both inequalities in the original coverage test without comparing
    every possible shift with every unresolved obligation.
    """
    scores = [0]*len(candidates)
    for pool in dict.fromkeys(c['pool'] for c in candidates):
        work = sorted((t.get('planning_release',t['release']), t.get('planning_deadline',t['deadline'])) for t in unmet
                      if pool == 'shared' or pool == t['service'])
        deadlines = sorted({deadline for _,deadline in work})
        tree = [0]*(len(deadlines)+1)
        inserted = 0
        for index in sorted((i for i,c in enumerate(candidates) if c['pool']==pool),
                            key=lambda i:candidates[i]['end']):
            c = candidates[index]
            while inserted < len(work) and work[inserted][0] < c['end']:
                slot = bisect_left(deadlines, work[inserted][1])+1
                while slot < len(tree):
                    tree[slot] += 1;slot += slot & -slot
                inserted += 1
            slot = bisect_left(deadlines, c['start']);expired = 0
            while slot:
                expired += tree[slot];slot -= slot & -slot
            scores[index] = inserted-expired
    return scores


def neighbours(config, settings, arrangement, current):
    roster = [{k:v for k,v in r.items() if k != 'id'} for r in current['roster']]
    candidates = shift_candidates(config, settings, arrangement)
    if current['passed']:
        for i in range(len(roster)):
            yield roster[:i]+roster[i+1:]
        for i, old in enumerate(roster):
            nearby = [c for c in candidates if c['pool'] == old['pool'] and
                      abs(c['start']-old['start']) <= 3600 and c['end']-c['start'] <= old['end']-old['start']]
            for c in sorted(nearby, key=lambda r:(r['end']-r['start'], abs(r['start']-old['start']),r['start'])):
                if c != old:
                    trial = roster[:i]+[c]+roster[i+1:]
                    if roster_within_limits(trial, settings):
                        yield trial
    else:
        scores = coverage_scores(candidates, current['unresolved'])
        ordered = sorted(range(len(candidates)), key=lambda i:(
            -scores[i]/((candidates[i]['end']-candidates[i]['start'])/3600),
            candidates[i]['start'], candidates[i]['pool']))
        if arrangement == 'dedicated':
            # Seed all category teams together. Absolute task counts otherwise
            # let a high-volume service consume the entire bounded search.
            seed = list(roster)
            for pool in settings['services']:
                if not any(r['pool']==pool for r in roster):
                    choice = next((candidates[i] for i in ordered if candidates[i]['pool']==pool and scores[i]), None)
                    if choice is not None:seed.append(choice)
            if seed != roster and roster_within_limits(seed, settings):
                yield seed
            obligations = {pool:sum(t['service']==pool for t in current['tasks']) for pool in settings['services']}
            hours = {pool:sum(r['end']-r['start'] for r in roster if r['pool']==pool) for pool in settings['services']}
            completed = current.get('services', {})
            ordered.sort(key=lambda i:(
                completed.get(candidates[i]['pool'], {}).get('completed', 0)/max(1, obligations[candidates[i]['pool']]),
                hours[candidates[i]['pool']]/max(1, obligations[candidates[i]['pool']])))
        # Evaluate alternative placements before increasing staffing again.
        for i in ordered:
            c = candidates[i]
            if scores[i] and roster_within_limits(roster+[c], settings):
                yield roster+[c]


def structural_findings(config, settings, result):
    """Check individual obligations with flexible lift packing, never a full round.

    This is not an inference from a failed deadline or scarce stock, and does
    not invent future demand from rules that emitted no work in this period.
    """
    floors={v['name']:v.get('floor',0) for v in config.get('locations',[])}
    lifts=config.get('lifts',[])
    lift_defaults=dict(length_m=2.8,width_m=1.8,height_m=2.1)
    from types import SimpleNamespace
    from amr_payload_inputs import payload_dimensions
    from amr_contingency_packing import lift_rectangles,pack_lift,PackingLimitError
    payloads={p['name']:SimpleNamespace(length_m=payload_dimensions(p)[0],width_m=payload_dimensions(p)[1],
        height_m=payload_dimensions(p)[2],allowed_carry_orientations=p.get('allowed_carry_orientations',['lengthways','sideways']))
        for p in config.get('payloads',[])}
    findings={}
    for task in result['tasks']:
        service=task['service'];profile=settings['profiles'][service]
        locations=[task['pickup'],task['dropoff'],profile['base']]
        if service in findings or any(name not in floors for name in locations):continue
        if len({floors[name] for name in locations}) <= 1:continue
        if task['payload'] not in payloads:continue
        rectangles=lift_rectangles(payloads,profile,[SimpleNamespace(payload=task['payload'],quantity=task.get('quantity',1))])
        try:
            fits=any(pack_lift(*(lift.get('capacity_'+k,lift_defaults[k]) for k in ('length_m','width_m','height_m')),
                               rectangles) is not None for lift in lifts)
        except PackingLimitError:
            continue  # A bounded packing search is not proof of infeasibility.
        if fits:continue
        findings[service]=(f"{service}: {task['payload']} and the person fit no configured lift, "
            f"even with permitted rotations, but generated work needs travel between floors "
            f"({task['pickup']} → {task['dropoff']}, base {profile['base']}). "
            'Review payload/person dimensions and lift capacity; extra staff cannot resolve this.')
    return list(findings.values())


def evaluate_study(path, *, cancelled=lambda:False, progress=lambda value:None):
    path = Path(path)
    with study_lock(path):
        state = load_study(path, for_resume=True)
        settings, config = state['settings'], state['configuration']
        cancel_path = Path(str(path)+'.cancel')
        next_cancel_check = 0.0
        cancel_requested = False
        def stopping():
            nonlocal next_cancel_check,cancel_requested
            if cancelled():return True
            now=perf_counter()
            if now >= next_cancel_check:
                cancel_requested=cancel_path.exists();next_cancel_check=now+.1
            return cancel_requested
        state['status'] = 'running'
        save_study(path,state)
        empty_result=next((r['current'] for r in state['variants'].values()
                           if r.get('current') and not r['current']['roster']),None)
        try:
            for name in VARIANTS:
                arrangement, timing = name.split('_')
                record = state['variants'].setdefault(name, dict(trials=0, tested=[], status='ready',
                    best=None, current=None, frontier=[]))
                if record['status'] in ('complete','infeasible'):
                    continue
                budget = settings['trial_budget']
                while record['trials'] < budget:
                    if stopping():
                        raise StudyCancelled()
                    if record['current'] is None:
                        roster = []
                    else:
                        if not record['frontier']:
                            tested=set(record['tested'])
                            record['frontier'] = list(islice((r for r in neighbours(config, settings, arrangement, record['current'])
                                                   if roster_key(r) not in tested),24))
                        if not record['frontier']:
                            record['status'] = 'complete'
                            break
                        roster = record['frontier'][0]
                    trial_start=perf_counter()
                    def trial_progress(value):
                        progress(dict(variant=name,trials=record['trials'],budget=budget,phase='simulating',
                            trial=record['trials']+1,elapsed_seconds=round(perf_counter()-trial_start,1),
                            best_hours=record['best']['staffed_hours'] if record['best'] else None,**value))
                    trial_progress(dict(simulated_hours=0,horizon_hours=0,completed=0))
                    if not roster and empty_result is not None:
                        result=empty_result
                    else:
                        result = simulate_candidate(config, settings, roster, buffered=timing == 'buffered',
                                                    cancelled=stopping,progress=trial_progress)
                        if not roster:empty_result=result
                    if record['frontier']:
                        record['frontier'].pop(0)
                    record['trials'] += 1
                    record['tested'].append(roster_key(roster))
                    findings=structural_findings(config,settings,result)
                    if findings:
                        record.update(current=result,status='infeasible',diagnostics=findings,frontier=[])
                        save_study(path,state)
                        progress(dict(variant=name,trials=record['trials'],budget=budget,status='infeasible',
                                      diagnostics=findings))
                        break
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
                if record['status'] not in ('complete','infeasible'):
                    record['status'] = 'budget_exhausted'
                save_study(path,state)
            state['status'] = ('infeasible' if any(r['status']=='infeasible' for r in state['variants'].values()) else
                'complete' if all(r['status']=='complete' for r in state['variants'].values()) else 'budget_exhausted')
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
