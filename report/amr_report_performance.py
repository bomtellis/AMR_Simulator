"""Compare recorded logistics performance at a common simulated checkpoint."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
import re

import pandas as pd

from amr_event_store import iter_events
from amr_route_analysis import CONFIRMED, COMPLETIONS, MOVE_TYPES, TOLERANCE, load_analysis, task_ids
from amr_sim_payload_instances import is_empty_payload_name
from amr_simulation_inputs import simulation_horizon_seconds
from amr_report_analysis import is_physical_amr_id
from amr_report_kpis import COMPLETE_EVENTS, FAIL_EVENTS, REQUEST_EVENTS, canonical_stream, clean, details, number, total


ASSIGNMENTS = {'task_assigned', 'multi_stop_task_assigned'}
REQUEST_RECORDS = REQUEST_EVENTS - ASSIGNMENTS


@dataclass(frozen=True)
class Request:
    release: float
    deadline: float | None
    stream: str
    pickup: str
    destination: str
    payload: str
    quantity: float


@dataclass
class Observation:
    requests: dict = field(default_factory=dict)
    completed: dict = field(default_factory=dict)
    failures: dict = field(default_factory=dict)
    confirmations: dict = field(default_factory=dict)
    profiles: dict = field(default_factory=dict)
    onboard: dict = field(default_factory=dict)
    busy_minutes: float = 0.0
    wait_p95_minutes: float | None = None
    funnel: Counter = field(default_factory=Counter)

    def planned(self, checkpoint):
        return {identity: request for identity, request in self.requests.items()
                if request.deadline is not None and request.deadline <= checkpoint}


def ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator else None


def service_request(identity, row):
    idle_return = identity.startswith('RETURN-') and is_empty_payload_name(row.get('payload'))
    return identity and not idle_return and row.get('task_source') != 'idle_return'


def request_from_event(row, identity, time):
    info = details(row.get('details'))
    release = number(info.get('original'))
    if release is None:
        release = number(row.get('task_release_time_sec'))
    if release is None:
        release = time
    deadline = number(info.get('deadline'))
    if deadline is None:
        target = number(row.get('task_target_time_sec'))
        if target:
            deadline = release + target
    category = canonical_stream(info.get('category')) or canonical_stream(row.get('task_source'))
    if category is None:
        match = re.search(r'(?:^|_)GEN_([A-Z0-9]+)', identity, re.I)
        category = canonical_stream(match[1]) if match else None
    return Request(release, deadline, category or 'Unclassified', clean(row.get('from_location')),
                   clean(info.get('final_destination') or row.get('to_location')), clean(row.get('payload')),
                   number(info.get('quantity')) or 1.)


def read_observation(path, checkpoint):
    result = Observation()
    generated, assigned, failures = {}, defaultdict(list), {}
    completions = {}
    activity, lift_wait = defaultdict(list), defaultdict(list)
    seen = set()
    for row in iter_events(path):
        moment = number(row.get('sim_time_sec'))
        if moment is None:
            continue
        kind = clean(row.get('event_type'))
        if moment > checkpoint and kind not in REQUEST_RECORDS:
            continue
        event_id = clean(row.get('event_id'))
        if event_id:
            if event_id in seen:
                continue
            seen.add(event_id)
        identity, amr = clean(row.get('task_id')), clean(row.get('amr_id'))
        profile = clean(row.get('route_profile'))
        if profile and identity and ',' not in identity:
            result.profiles[identity] = profile
        if kind in COMPLETIONS and event_id:
            result.confirmations[event_id] = moment
        if kind in REQUEST_RECORDS and service_request(identity, row):
            request = request_from_event(row, identity, moment)
            if request.release <= checkpoint:
                source = result.requests if kind == 'task_released' else generated
                source.setdefault(identity, request)
        elif kind in COMPLETE_EVENTS and identity:
            completions.setdefault(identity, moment)
        elif kind in FAIL_EVENTS and identity:
            failures.setdefault(identity, (moment, clean(row.get('pending_reason')) or clean(row.get('details'))))
        if kind in ASSIGNMENTS and is_physical_amr_id(amr):
            assigned[identity].append((moment, amr))
        if not kind.removeprefix('multi_stop_').startswith('segment_') or not is_physical_amr_id(amr):
            continue
        segment = clean(row.get('segment_type')) or kind.removeprefix('multi_stop_').removeprefix('segment_')
        if event_id and segment in MOVE_TYPES:
            raw_onboard = clean(row.get('onboard_payloads'))
            if raw_onboard and raw_onboard != '[]':
                try:
                    payloads = json.loads(raw_onboard)
                except ValueError:
                    payloads = []
                if isinstance(payloads, list):
                    tasks = tuple(item['task_id'] for item in payloads if isinstance(item, dict)
                                  and isinstance(item.get('task_id'), str) and item['task_id'])
                    if tasks:
                        result.onboard[event_id] = tasks
        duration = number(row.get('duration_sec'))
        if not duration or segment in ('idle', 'parked'):
            continue
        end = min(moment + duration, checkpoint)
        activity[amr].append((moment, end))
        if segment in ('wait_for_lift', 'lift_reposition'):
            for task in task_ids(row):
                lift_wait[task].append((moment, end))

    for identity, request in generated.items():
        result.requests.setdefault(identity, request)
    result.completed = {identity: end for identity, end in completions.items() if identity in result.requests}
    result.failures = {identity: reason for identity, (_, reason) in failures.items()
                       if identity in result.requests and identity not in result.completed}
    for identity, bookings in assigned.items():
        failure = failures.get(identity, (checkpoint, ''))[0]
        terminal = completions.get(identity, failure)
        bookings.sort()
        for index, (start, amr) in enumerate(bookings):
            next_start = bookings[index + 1][0] if index + 1 < len(bookings) else checkpoint
            activity[amr].append((start, min(terminal, next_start)))
    result.busy_minutes = sum(total(intervals) for intervals in activity.values()) / 60
    waits = [total((start, min(end, finish)) for start, end in lift_wait[identity]) / 60
             for identity, finish in result.completed.items()]
    if waits:
        result.wait_p95_minutes = float(pd.Series(waits).quantile(.95))
    return result


def funnel_scope(config):
    building = config.get('building', {})
    preference = building.get('forced_floor_lift_preference') or {}
    origin, hub = preference.get('from_floor'), building.get('force_via_floor')
    selected = preference.get('lift_ids')
    if type(origin) is int and type(hub) is int and selected:
        return origin, hub, frozenset(selected)
    return None


def assess_funnel(run, scope, observation, checkpoint):
    origin, hub, selected = scope
    fixed_exits = {lift['id'] for lift in run.config.get('lifts', [])
                   if lift.get('transfer_timing_mode', 'fixed') == 'fixed'
                   and number(lift.get('boarding_time_sec')) is not None}
    counts = Counter()
    for leg in run.legs:
        movement = [segment for segment in leg.segments if segment.kind in MOVE_TYPES]
        if not movement or movement[0].start[2] != origin or leg.time is None or leg.time > checkpoint:
            continue
        rides = [segment for segment in movement if segment.kind == 'lift_transfer']
        if origin == hub and not rides and movement[-1].finish[2] == hub:
            continue
        if leg.end is not None and leg.end > checkpoint + TOLERANCE:
            continue
        if not run.complete or leg.evidence != CONFIRMED or not any(identity in observation.confirmations
                                                                  for identity in leg.confirmation_ids):
            counts['unverified'] += 1
            continue
        carried = next((observation.onboard[s.id] for s in movement if s.id in observation.onboard), ())
        # Older records can copy a task's profile onto the approach before it applies.
        profiled = (any(identity in observation.profiles for identity in carried) if carried else
                    leg.profile and leg.purpose in ('Delivery', 'Return'))
        if profiled:
            counts['exempt'] += 1
            continue
        if any(s.start[2] is None or s.finish[2] is None or not s.lift for s in rides):
            counts['unverified'] += 1
            continue
        hub_rides = [s for s in rides if hub in (s.start[2], s.finish[2])]
        arrivals = [s for s in hub_rides if s.finish[2] == hub]
        visited = origin == hub or any(number(s.detail.get('exit_time_sec')) is not None
                                      or s.lift in fixed_exits for s in arrivals)
        if arrivals and not visited:
            counts['unverified'] += 1
            continue
        counts['compliant' if visited and all(s.lift in selected for s in hub_rides) else 'outside'] += 1
    return counts


def routing_mode(config):
    building = config.get('building', {})
    if building.get('force_via_floor_enabled') is not True:
        return 'Forced-floor routing off'
    mode = (building.get('forced_floor_lift_preference') or {}).get('mode', 'off')
    label = {'off': 'Preference off', 'prefer': 'Prefer with fallback', 'required': 'Selected lifts only'}.get(mode, mode)
    return f"{label} via level {building.get('force_via_floor')}"


def compare(baseline_path, baseline_config, scenario_path, scenario_config, *, baseline_name, scenario_name):
    checkpoint = min(simulation_horizon_seconds(baseline_config), simulation_horizon_seconds(scenario_config))
    if checkpoint <= 0:
        raise ValueError('The saved runs have no shared simulation window.')
    baseline = read_observation(baseline_path, checkpoint)
    scenario = read_observation(scenario_path, checkpoint)
    scope = funnel_scope(scenario_config) or funnel_scope(baseline_config)
    if scope:
        for observation, path in ((baseline, baseline_path), (scenario, scenario_path)):
            observation.funnel = assess_funnel(load_analysis(path, drawings=False), scope, observation, checkpoint)
    return comparison_results(baseline, scenario, checkpoint, scope, baseline_config, scenario_config,
                              baseline_name, scenario_name)


def comparison_results(base, trial, checkpoint, scope, base_config, trial_config, base_name, trial_name):
    base_due, trial_due = base.planned(checkpoint), trial.planned(checkpoint)
    base_assessed = {key: request for key, request in base.requests.items() if request.deadline is not None}
    trial_assessed = {key: request for key, request in trial.requests.items() if request.deadline is not None}
    matched = base.requests == trial.requests
    same_start = base_config.get('simulation', {}).get('start_datetime') == trial_config.get('simulation', {}).get('start_datetime')
    base_spi = ratio(len(base.completed.keys() & base_assessed.keys()), len(base_due))
    trial_spi = ratio(len(trial.completed.keys() & trial_assessed.keys()), len(base_due)) if matched and same_start else None
    base_standard = ratio(base.busy_minutes, len(base.completed)) if base.busy_minutes > 0 else None
    trial_cpi = ratio(base_standard * len(trial.completed), trial.busy_minutes) if base_standard is not None else None
    wait_ratio = ratio(trial.wait_p95_minutes, base.wait_p95_minutes)

    def stats(observation, due):
        on_time = sum(observation.completed.get(identity, float('inf')) <= request.deadline
                      for identity, request in due.items())
        checked = observation.funnel['compliant'] + observation.funnel['outside']
        return dict(requests=len(observation.requests), completed=len(observation.completed), due=len(due),
                    failed=len(observation.failures), overdue_unfinished=len(due.keys() - observation.completed.keys() - observation.failures.keys()),
                    route_failures=sum(bool(re.search(r'no (?:permitted amr |graph/lift |)route', reason, re.I))
                                       for reason in observation.failures.values()),
                    no_deadline=sum(request.deadline is None for request in observation.requests.values()),
                    busy=observation.busy_minutes, wait=observation.wait_p95_minutes, sla=ratio(on_time, len(due)),
                    on_time=on_time, funnel=ratio(observation.funnel['compliant'], checked),
                    checked=checked, compliant=observation.funnel['compliant'], exempt=observation.funnel['exempt'],
                    unverified=observation.funnel['unverified'])

    def streams(observation, due):
        counts = defaultdict(Counter)
        for identity, request in due.items():
            counts[request.stream]['due'] += 1
            counts[request.stream]['on_time'] += observation.completed.get(identity, float('inf')) <= request.deadline
        return counts

    baseline, scenario = stats(base, base_due), stats(trial, trial_due)
    baseline.update(spi=base_spi, cpi=1. if base_standard is not None else None,
                    wait_ratio=1. if base.wait_p95_minutes else None)
    scenario.update(spi=trial_spi, cpi=trial_cpi, wait_ratio=wait_ratio)
    differences = [label for key, label in (('simulation', 'simulation settings'), ('task_generation', 'demand rules'),
                   ('tasks', 'scheduled tasks'), ('amrs', 'fleet'), ('lifts', 'lift definitions'),
                   ('corridors', 'corridors'), ('locations', 'locations'), ('route_profiles', 'route profiles'))
                   if base_config.get(key) != trial_config.get(key)]
    base_routing, trial_routing = ({k: v for k, v in cfg.get('building', {}).items() if k != 'forced_floor_lift_preference'}
                                   for cfg in (base_config, trial_config))
    if base_routing != trial_routing:
        differences.append('building settings other than lift preference')
    return dict(baseline=baseline, scenario=scenario, baseline_name=base_name, scenario_name=trial_name,
                baseline_mode=routing_mode(base_config), scenario_mode=routing_mode(trial_config),
                baseline_streams=streams(base, base_due), scenario_streams=streams(trial, trial_due),
                checkpoint=checkpoint, scope=scope, matched=matched and same_start, differences=differences)
