"""Shared AMR entry/exit timing; legacy fixed timing remains the default."""
import math


def transfer_seconds(lift, amr, entry_distance=None, exit_distance=None):
    if getattr(lift, 'transfer_timing_mode', 'fixed') == 'fixed':
        seconds = float(lift.boarding_time_sec)
        return seconds, seconds
    if amr is None:
        raise ValueError('Speed-based lift timing requires an AMR.')
    result = []
    for direction, distance in (('entry', entry_distance), ('exit', exit_distance)):
        speed = getattr(amr, 'lift_' + direction + '_speed_m_per_sec', None)
        if any(v is None or isinstance(v, bool) or not math.isfinite(float(v)) or float(v) <= 0
               for v in (distance, speed)):
            raise ValueError(f'Lift {lift.id}: positive {direction} distance and AMR speed are required.')
        seconds = float(distance) / float(speed)
        if not math.isfinite(seconds):
            raise ValueError(f'Lift {lift.id}: {direction} graph distance/speed produces a nonfinite transfer time.')
        result.append(seconds)
    return tuple(result)


def transfer_input_findings(config):
    lifts = config.get('lifts', [])
    robots = config.get('amrs', [])
    if not isinstance(lifts, list) or not isinstance(robots, list):
        return
    enabled = False
    for index, lift in enumerate(lifts):
        if not isinstance(lift, dict):
            continue
        mode = lift.get('transfer_timing_mode', 'fixed')
        path = f'/lifts/{index}'
        if mode not in ('fixed', 'speed_based'):
            yield path + '/transfer_timing_mode', 'Transfer timing mode must be fixed or speed_based.'
        enabled |= mode == 'speed_based'
    for index, robot in enumerate(robots):
        if not isinstance(robot, dict):
            continue
        for direction in ('entry', 'exit'):
            key = 'lift_' + direction + '_speed_m_per_sec'
            required = enabled and robot.get('quantity', 1) != 0
            if key not in robot and not required:
                continue
            if not positive(robot.get(key)):
                yield f'/amrs/{index}/{key}', f'{key} must be finite and positive in metres/second for speed-based lifts.'


def positive(value):
    try:
        return value is not None and not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def graph_transfer_connectors(sim, amr, start, finish, origin, destination, payload, rules, orientation):
    """Resolve the actual terminal graph edges; never infer distances from car size.

    For an intermediate landing the next route starts outside the car, after
    the exit edge. An isolated start/finish at a lift uses a deterministic valid
    incident edge, so an actual alighting/boarding stop is still represented.
    """
    width = sim._required_corridor_width(amr, payload, orientation)

    def route(a, b):
        return sim._shortest_path_same_floor(a.floor, a.name, b.name,
                                             rules=rules, minimum_width_m=width)

    def connector(a, b, entering):
        path = route(a, b)
        if path is None:
            return None
        if path['edges']:
            return path['edges'][-1 if entering else 0]
        lift = b if entering else a
        candidates = []
        for name in sim.floor_graphs.get(lift.floor, {}):
            if name in sim.lift_stop_names:
                continue
            neighbor = sim.graph_nodes[name]
            link = route(neighbor, lift) if entering else route(lift, neighbor)
            if link and len(link['edges']) == 1:
                candidates.append(link['edges'][0])
        return min(candidates, key=lambda e: (e['distance_m'], e['from'], e['to'])) if candidates else None

    entry = connector(start, origin, True)
    exit = connector(destination, finish, False)
    if entry is None or exit is None:
        return None
    if not positive(entry['distance_m']) or not positive(exit['distance_m']):
        raise ValueError('Speed-based lift timing requires positive graph connector edge distances.')
    return entry, exit


def connector_journey_slot(sim, lift, arrival, origin_floor, destination_floor, amr,
                           transfer_times, entry_edge, exit_edge, prior_journeys):
    """Include connector traffic in a read-only lift-slot search."""
    requested = arrival
    base_times = transfer_times
    for _ in range(128):
        slot = sim._find_lift_journey_slot(lift, requested, origin_floor, destination_floor,
            amr=amr, transfer_times=transfer_times, prior_journeys=prior_journeys)
        if not math.isfinite(slot['lift_finish']):
            return None
        delay = 0.0
        resolved_times = []
        for index, (edge, start) in enumerate(((entry_edge, slot['entry_start_sec']),
                (exit_edge, slot['loaded_finish'] + lift.door_time_sec))):
            from amr_scenario_routing import departure_state
            allowed, factor, _ = departure_state(sim, amr, edge, start, base_times[index])
            if not math.isfinite(allowed):
                return None
            edge_key = sim._physical_edge_key(edge['from'], edge['to'])
            _, people_factor, _ = sim._people_on_edge(edge_key, allowed, base_times[index])
            congestion = max(sim.min_congestion_speed_factor,
                1.0 - sim._edge_recent_demand(edge_key, allowed) * sim.edge_slowdown_per_amr)
            duration = base_times[index] / max(.01, min(factor, people_factor, congestion))
            resolved_times.append(duration)
            ready, _ = sim._find_next_edge_start(
                edge_key=edge_key, requested_start=allowed,
                duration=duration, spacing_time=sim._spacing_time_sec(amr),
                directed_edge_key=(edge['from'], edge['to']), max_concurrency=1)
            safe_end = sim._find_next_node_arrival(edge['to'], ready + duration, sim._spacing_time_sec(amr))
            delay = max(delay, ready - start, safe_end - start - duration)
        if not math.isfinite(delay):
            return None
        if any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-9) for a, b in zip(transfer_times, resolved_times)):
            transfer_times = tuple(resolved_times)
            requested = slot['lift_start'] + delay
            continue
        if delay <= 1e-9:
            return slot
        requested = slot['lift_start'] + delay
    return None
