"""CPU baseline plus isolated, exact-output lift-planning experiments.

Prototypes are compiled as separate functions and never installed on Simulation.
Only read-only planning queries are replayed; this does not measure whole-run
speedups or prove equivalence for all model configurations.
"""
import argparse
import contextlib
import inspect
import io
import json
from pathlib import Path
import statistics
import sys
import textwrap
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'verification'))

from simulator import Simulation
from benchmark_computation import sample
from amr_sim_payload_instances import EMPTY_PAYLOAD_NAME


def prototype(function, *, tail=False, prune=False, early_stowed=False):
    source = textwrap.dedent(inspect.getsource(function))
    if tail:
        old = 'tail = max(reservations, key=lambda reservation: reservation[1])'
        assert source.count(old) == 1
        source = source.replace(old, 'tail = reservations[-1]')
    if prune:
        old = 'if not math.isfinite(lift_finish):\n            continue\n'
        assert source.count(old) == 1
        source = source.replace(old, old + '\n        if not self.geometric_motion and lift_finish >= best_finish:\n            continue\n')
    if early_stowed:
        guard = '    if self._amr_is_stowed_at_configured_charge_space(amr):\n        return None\n'
        assert source.count(guard) == 1
        source = source.replace(guard, '')
        assignment = '    charge_location = self._charge_location_for_idle_return(amr, now)'
        assert source.count(assignment) == 1
        source = source.replace(assignment, guard + '\n' + assignment)
    namespace = {}
    exec(compile(source, '<isolated CPU planning prototype>', 'exec'), function.__globals__, namespace)
    return namespace[function.__name__]


def replay_idle_guard(output):
    from copy import deepcopy
    from tests.test_route_reservation_atomicity import resource_state
    config = json.loads((ROOT / 'ltn.json').read_text(encoding='utf-8-sig'))
    with contextlib.redirect_stdout(io.StringIO()):
        sim = Simulation(config, verbose=False, defer_exports=True)
    original = Simulation._create_idle_return_task
    early = prototype(original, early_stowed=True)
    robots = [robot for robot in sim.amrs if sim._amr_is_stowed_at_configured_charge_space(robot)]
    assert robots, 'LTN initial state has no stowed robots to replay'
    queries = [(robot, when) for when in (0, 3600, 86400) for robot in robots]
    before = deepcopy(resource_state(sim))
    with contextlib.redirect_stdout(io.StringIO()):
        expected = [original(sim, *query) for query in queries]
        actual = [early(sim, *query) for query in queries]
    assert all(value is None for value in expected + actual)
    assert before == resource_state(sim), 'Idle replay changed operational resources'
    timings = {'original': [], 'prototype': []}
    for repeat in range(5):
        order = [('original', original), ('prototype', early)]
        if repeat % 2:
            order.reverse()
        for name, function in order:
            started = time.perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                for query in queries:
                    function(sim, *query)
            timings[name].append(time.perf_counter() - started)
    medians = {name: statistics.median(values) for name, values in timings.items()}
    result = dict(cpu_only=True, state='Initial LTN placement', robots=len(robots), queries=len(queries),
        exact_return_parity=True, operational_resource_parity=True, samples_sec=timings,
        medians_sec=medians, speedup=medians['original'] / medians['prototype'],
        caveat='Isolated stowed-robot calls, with warm static caches; not a whole-run speedup. '
               'The production simulator was not changed.')
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    if sim.event_store is not None:
        sim.event_store.close()


def replay(sim, output):
    assert not sim.parallel_routing_enabled
    histories = sim.lift_reservations
    ordered = {lift.id for lift in sim.lifts
               if lift.health_loss_per_journey_percent > 0
               or lift.mean_time_between_failures_hours > 0}
    tail_is_last = all(max(rows, key=lambda row: row[1]) == rows[-1]
                       for identity, rows in histories.items() if rows and identity in ordered)
    assert tail_is_last
    original_slot = Simulation._find_lift_journey_slot
    tail_slot = prototype(original_slot, tail=True)
    slot_queries = [(lift, sim.current_time + delta, origin, destination)
                    for lift in sim.lifts for origin in lift.served_floors
                    for destination in lift.served_floors if origin != destination
                    for delta in (0, 60, 3600)]
    original_plan = Simulation._nearest_compatible_lift_plan
    pruned_plan = prototype(original_plan, prune=True)
    empty = sim.payloads[EMPTY_PAYLOAD_NAME]
    locations = sorted(sim.locations.values(), key=lambda value: value.name)
    # Deterministic sample of actual service locations and final robot state.
    plan_queries = []
    for robot_index, robot in enumerate(sim.amrs):
        start = sim._robot_location(robot)
        destinations = [value for value in locations if value.floor != start.floor]
        for index in range(min(12, len(destinations))):
            destination = destinations[(index * 17 + robot_index * 7) % len(destinations)]
            plan_queries.append((sim.current_time, robot, start, destination, empty))

    def compare(left, right, queries):
        with contextlib.redirect_stdout(io.StringIO()):
            expected = [left(sim, *query) for query in queries]
            actual = [right(sim, *query) for query in queries]
        assert expected == actual, 'Read-only prototype changed a query result'
        timings = {'original': [], 'prototype': []}
        for repeat in range(5):
            order = [('original', left), ('prototype', right)]
            if repeat % 2:
                order.reverse()
            for name, function in order:
                start = time.perf_counter()
                with contextlib.redirect_stdout(io.StringIO()):
                    for query in queries:
                        function(sim, *query)
                timings[name].append(time.perf_counter() - start)
        medians = {name: statistics.median(values) for name, values in timings.items()}
        return dict(queries=len(queries), exact_plan_parity=True, samples_sec=timings,
                    medians_sec=medians, speedup=medians['original'] / medians['prototype'],
                    successful_queries=sum(value is not None for value in expected))

    result = dict(cpu_only=True, simulation_time_sec=sim.current_time,
        reservation_counts={identity: len(rows) for identity, rows in histories.items()},
        last_booking_matches_max_finish=tail_is_last,
        append_only_tail=compare(original_slot, tail_slot, slot_queries),
        prune_nonwinning_lift=compare(original_plan, pruned_plan, plan_queries),
        caveat='Isolated read-only queries on final LTN state, with warm static caches. '
               'Ratios are not whole-simulation speedups. Prototypes were never used during the baseline run.')
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--idle-guard-only', action='store_true')
    parser.add_argument('--early-idle-guard-run', action='store_true',
                        help='Run the full CPU model with only the isolated early-stowed prototype.')
    args = parser.parse_args()
    if args.idle_guard_only:
        replay_idle_guard(args.output)
        raise SystemExit(0)
    captured = []
    original_init = Simulation.__init__
    original_idle = Simulation._create_idle_return_task
    if args.early_idle_guard_run:
        Simulation._create_idle_return_task = prototype(original_idle, early_stowed=True)

    def capture(instance, *values, **keywords):
        original_init(instance, *values, **keywords)
        captured.append(instance)

    Simulation.__init__ = capture
    try:
        sample('cpu', args.output)
    finally:
        Simulation.__init__ = original_init
        Simulation._create_idle_return_task = original_idle
    if args.early_idle_guard_run:
        import hashlib
        result = json.loads(args.output.read_text(encoding='utf-8'))
        result['experiment'] = 'Only move the existing stowed check before charging-destination planning.'
        result['prototype_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        result['prototype_source'] = str(Path(__file__).resolve())
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('Isolated early-idle-guard CPU run complete.', flush=True)
        raise SystemExit(0)
    print('CPU baseline complete; replaying isolated lift queries.', flush=True)
    replay(captured[0], args.output.with_suffix('.replay.json'))
