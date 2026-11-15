"""Floor waypoint policy and read-only planning of connecting lift journeys."""
import heapq
import itertools
import math
from copy import copy


def minimum_lift_journey_seconds(lift, origin, destination):
    stationary = 2 * lift.door_time_sec
    if getattr(lift, 'transfer_timing_mode', 'fixed') == 'fixed':
        stationary += 2 * lift.boarding_time_sec
    return stationary + abs(destination - origin) / max(lift.speed_floors_per_sec, 1e-9)


def optimistic_remaining_times(sim, amr, finish, via, final_lift=None, final_distance=None,
                               *, allowed_lifts=None, required_floor_lifts=None,
                               finish_by=None, lift_openings=None, final_options=()):
    """Consistent lower bounds, ignoring waits, restrictions, wear and outages.

    Route comparisons can discard states whose optimistic completion is later
    than a known feasible route.

    With a deadline, omit routes that would need to start a lift journey
    before the earliest it could be booked.
    """
    if sim.scenario_mode or sim.geometric_motion or sim.parallel_routing_enabled:
        return None
    speed = max(1e-9, float(amr.speed_m_per_sec),
                float(getattr(amr, 'lift_entry_speed_m_per_sec', 0) or 0),
                float(getattr(amr, 'lift_exit_speed_m_per_sec', 0) or 0))
    signature = (id(sim.floor_graphs), speed, tuple(
        (lift.id, tuple(lift.served_floors), lift.speed_floors_per_sec,
         lift.door_time_sec, lift.boarding_time_sec,
         getattr(lift, 'transfer_timing_mode', 'fixed')) for lift in sim.lifts))
    graphs = getattr(sim, '_lift_bound_graphs', None)
    if graphs is None:
        graphs = sim._lift_bound_graphs = {}
    graph_cache = graphs.get(signature)
    if graph_cache is None:
        # A corridor can end at a lift, but cannot use that lift landing as
        # an intermediate shortcut. Distinguish arrival from boarding.
        stops = sim.lift_stop_names
        reverse = {(name, False): [] for name in sim.graph_nodes}
        for name in stops:
            reverse[(name, True)] = [((name, False), 0.0, None)]
        for graph in sim.floor_graphs.values():
            for origin, edges in graph.items():
                for edge in edges:
                    target = edge['to']
                    reverse[(target, target in stops)].append(
                        ((origin, False), max(0.0, edge['distance_m']) / speed, None))
        for lift in sim.lifts:
            for origin in lift.served_floors:
                for destination in lift.served_floors:
                    if origin != destination:
                        seconds = minimum_lift_journey_seconds(lift, origin, destination)
                        reverse[(f'{lift.id}-F{destination}', False)].append(
                            ((f'{lift.id}-F{origin}', True), seconds, (lift.id, (origin, destination))))
        graph_cache = (reverse, {}, {})
        if len(graphs) >= 4:
            graphs.pop(next(iter(graphs)))
        graphs[signature] = graph_cache
    reverse, cache, deadline_cache = graph_cache
    terminals = ((final_lift, final_distance),) if final_lift is not None else final_options
    cache_key = (finish.name, via, final_lift.id if final_lift else None, final_distance,
                 allowed_lifts, required_floor_lifts,
                 tuple((lift.id, distance) for lift, distance in final_options))
    cache_limit = 64
    if finish_by is not None:
        cache = deadline_cache
        cache_limit = 32
        # An omitted car never contributes a path to this bound.
        openings = frozenset((lift_id, opening) for lift_id, opening in lift_openings.items()
                             if allowed_lifts is None or lift_id in allowed_lifts)
        cache_key += (finish_by, openings, tuple(lift_openings[lift.id] for lift, _ in terminals))
    if cache_key in cache:
        return cache[cache_key]
    if not terminals:
        distances = {((finish.name, False), True): 0.0}
        if finish.name in sim.lift_stop_names:
            distances[((finish.name, True), True)] = 0.0
    else:
        # Relax the approach to every possible boarding stop of this final
        # car. The terminal ride must use that car; restrictions, waits and
        # connector traffic remain omitted. Destination distance is the
        # permitted static minimum, never longer than a real final walk.
        distances = {}
        visited_options = (False, True) if finish.floor == via else (True,)
        for lift, distance in terminals:
            for floor in lift.served_floors:
                if floor == finish.floor:
                    continue
                if (required_floor_lifts is not None and via in (floor, finish.floor)
                        and lift.id not in required_floor_lifts):
                    continue
                seconds = minimum_lift_journey_seconds(lift, floor, finish.floor) + distance / speed
                if finish_by is not None and finish_by - seconds < lift_openings[lift.id]:
                    continue
                for visited in visited_options:
                    distances[((f'{lift.id}-F{floor}', True), visited)] = seconds
    queue = [(seconds, node, visited) for (node, visited), seconds in distances.items()]
    heapq.heapify(queue)
    while queue:
        seconds, node, visited = heapq.heappop(queue)
        if seconds != distances.get((node, visited)):
            continue
        enters_via = sim.graph_nodes[node[0]].floor == via
        if enters_via and not visited:
            continue
        predecessors = (False, True) if enters_via else (visited,)
        for origin, cost, lift_edge in reverse[node]:
            if lift_edge is not None:
                lift_id, floors = lift_edge
                if allowed_lifts is not None and lift_id not in allowed_lifts:
                    continue
                if required_floor_lifts is not None and via in floors and lift_id not in required_floor_lifts:
                    continue
            for prior_visited in predecessors:
                key = (origin, prior_visited)
                candidate = seconds + cost
                if (finish_by is not None and lift_edge is not None
                        and finish_by - candidate < lift_openings[lift_id]):
                    continue
                if candidate < distances.get(key, math.inf):
                    distances[key] = candidate
                    heapq.heappush(queue, (candidate, origin, prior_visited))
    distances = {(name, visited): seconds for ((name, boarding), visited), seconds in distances.items()
                 if not boarding}
    if len(cache) >= cache_limit:
        cache.pop(next(iter(cache)))
    cache[cache_key] = distances
    return distances


def required_waypoint(config, start_floor, end_floor):
    if start_floor == end_floor:
        return None
    for rule in config.get('building', {}).get('mandatory_floor_waypoints', []):
        if rule['from_floor'] == start_floor and end_floor in rule['to_floors']:
            return rule['via_floor']
    return None


def lift_policy_key(config):
    from amr_bed_lifts import policy_key
    building = config.get('building', {})
    legacy = (building.get('lift_transfer_floor'), tuple(building.get('destination_side_lift_floors', [])),
              tuple((r['from_floor'], tuple(r['to_floors']), r['via_floor'])
                    for r in building.get('mandatory_floor_waypoints', []))) + policy_key(config)
    if building.get('force_via_floor_enabled', False) is True:
        from amr_forced_floor import lift_preference_key
        forced = legacy + (('forced_floor', building['force_via_floor']),)
        preference = lift_preference_key(config)
        return forced + (preference,) if preference else forced
    return legacy


def destination_direct_plan(sim, ready_time, amr, start, finish, payload, rules,
                            orientation, collect_segments, prior_journeys=(), route_cache=None):
    """Choose by destination walking distance only on explicitly selected floors."""
    floors = sim.config.get('building', {}).get('destination_side_lift_floors', [])
    direct = sim._direct_lift_plan
    if start.floor not in floors or (rules or {}).get('bed_fallback_search'):
        return direct(ready_time, amr, start, finish, payload, rules, orientation,
                      collect_segments, prior_journeys=prior_journeys, _route_cache=route_cache)
    if sim.scenario_mode or sim.geometric_motion:
        # Preserve the original evaluation order for time-dependent routes.
        winner = winner_key = None
        for lift in sim.lifts:
            plan = direct(ready_time, amr, start, finish, payload, rules, orientation,
                          collect_segments, only_lift=lift.id, prior_journeys=prior_journeys)
            if plan is None:
                continue
            width = sim._required_corridor_width(amr, payload, orientation)
            walking = sim._shortest_path_same_floor(finish.floor,
                plan['destination_lift'].name, finish.name, rules=rules, minimum_width_m=width)
            if walking is None:
                continue
            key = (walking['distance_m'], plan['final_finish'], str(lift.id))
            if winner_key is None or key < winner_key:
                winner, winner_key = plan, key
        if winner is not None:
            winner = dict(winner, lift_selection_reason='destination_walking_distance',
                          destination_walking_distance_m=winner_key[0])
        return winner
    winner = None
    winner_key = None
    width = sim._required_corridor_width(amr, payload, orientation)
    candidates = []
    for lift in sim.lifts:
        if not lift.can_serve(start.floor, finish.floor):
            continue
        walking = sim._shortest_path_same_floor(finish.floor,
            sim._lift_location_on_floor(lift, finish.floor).name, finish.name,
            rules=rules, minimum_width_m=width)
        if walking is not None:
            candidates.append((walking['distance_m'], lift))
    # Original selection is lexicographic: distance, finish time, then lift ID.
    # Once a feasible distance is found, farther lifts cannot beat it. Still
    # evaluate every equal-distance candidate, including a busy nearest car.
    candidates.sort(key=lambda candidate: candidate[0])
    for walking_distance, lift in candidates:
        if winner_key is not None and walking_distance > winner_key[0]:
            break
        plan = direct(ready_time, amr, start, finish, payload, rules, orientation,
                      collect_segments, only_lift=lift.id, prior_journeys=prior_journeys,
                      _route_cache=route_cache)
        if plan is None:
            continue
        key = (walking_distance, plan['final_finish'], str(lift.id))
        if winner_key is None or key < winner_key:
            winner, winner_key = plan, key
    if winner is not None:
        winner = dict(winner, lift_selection_reason='destination_walking_distance',
                      destination_walking_distance_m=winner_key[0])
    return winner


def connecting_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                         orientation, collect_segments, *, finish_before=math.inf):
    """Search lift landings without mutating shared bookings during estimates.

    A landing is an actual alighting/boarding stop, not a floor passed inside
    a moving car. Every edge uses the existing horizontal/width/profile and
    lift scheduling checks. Earlier rides form a private booking overlay.
    """
    via = required_waypoint(sim.config, start.floor, finish.floor)
    direct = sim._direct_lift_plan
    # Read-only searches share one AMR/load/profile and a stable reservation
    # snapshot. Reuse exact (unrounded) same-floor queries only within that
    # search. Scenario/geometric queries keep their existing evaluation path.
    route_cache = {} if not sim.scenario_mode and not sim.geometric_motion else None
    fallback_search = (rules or {}).get('bed_fallback_search', False)
    initial_plan = None
    if via is None or via == finish.floor:
        plan = destination_direct_plan(sim, ready_time, amr, start, finish, payload, rules,
                                       orientation, collect_segments, route_cache=route_cache)
        if plan is not None and not fallback_search:
            return plan
        if plan is not None and plan['final_finish'] < finish_before:
            initial_plan = plan
    building = sim.config.get('building', {})
    if via is None:
        via = building.get('lift_transfer_floor')
    policy_enabled = (building.get('lift_transfer_floor') is not None
                      or bool(building.get('destination_side_lift_floors')))
    remaining = optimistic_remaining_times(sim, amr, finish, via)
    serial = itertools.count()
    queue = [(ready_time, next(serial), start, via is None or via == start.floor, ())]
    best = {}
    winner = initial_plan
    while queue:
        sim._check_run_cancelled()
        time, _, current, visited, journeys = heapq.heappop(queue)
        best_finish = winner['final_finish'] if winner is not None else finish_before
        if time >= best_finish:
            break
        # Do not invent lift up/down loops as a substitute for a missing
        # corridor connection. Real connecting routes visit each floor once.
        used_floors = frozenset([start.floor] + [leg['destination_lift'].floor for leg in journeys])
        key = (current.name, visited, used_floors)
        if time >= best.get(key, math.inf):
            continue
        best[key] = time
        if math.isfinite(best_finish) and remaining is not None:
            earliest = time + remaining.get((current.name, visited), math.inf)
            # Retain ties and allow ample round-off slack. The lower bound is
            # consistent along every real leg, so discarded descendants cannot
            # suppress a state capable of beating this existing winner either.
            slack = 1e-8 * max(1.0, abs(time), abs(best_finish))
            if earliest > best_finish + slack:
                continue
        if visited and policy_enabled and finish.floor not in used_floors:
            final = destination_direct_plan(sim, time, amr, current, finish, payload, rules,
                                            orientation, collect_segments, journeys, route_cache)
            if final is not None:
                if final['final_finish'] < best_finish:
                    winner = dict(journeys=journeys + (final,), final_finish=final['final_finish'])
                    best_finish = final['final_finish']
                # A suitable direct final ride takes priority over extra connections.
                if not fallback_search:
                    continue
        for lift in sim.lifts:
            if current.floor not in lift.served_floors or not sim._lift_allowed(lift, rules):
                continue
            for floor in lift.served_floors:
                if floor in used_floors:
                    continue
                satisfied = visited or floor == via
                if floor == finish.floor and not satisfied and route_cache is not None:
                    # Reaching the destination before the required stop can
                    # never finish: used_floors forbids returning there. Such
                    # states also cannot dominate any valid state, since their
                    # used-floor set already contains the final destination.
                    continue
                final_leg = floor == finish.floor and satisfied
                target = finish if final_leg else sim._lift_location_on_floor(lift, floor)
                next_key = (target.name, satisfied, used_floors | {floor})
                if not final_leg and time >= best.get(next_key, math.inf):
                    continue
                leg = direct(time, amr, current, target, payload, rules, orientation,
                             collect_segments, only_lift=lift.id, prior_journeys=journeys,
                             _route_cache=route_cache)
                if leg is None:
                    continue
                target = leg.get('routing_end_location', target)
                next_key = (target.name, satisfied, used_floors | {floor})
                path = journeys + (leg,)
                if final_leg:
                    if leg['final_finish'] < best_finish:
                        winner = dict(journeys=path, final_finish=leg['final_finish'])
                        best_finish = leg['final_finish']
                elif leg['final_finish'] < best.get(next_key, math.inf):
                    heapq.heappush(queue, (leg['final_finish'], next(serial), target, satisfied, path))
    return winner


def lift_plan_journeys(plan):
    return plan.get('journeys', (plan,))


def advance_lift_wear(lift, operating_seconds, finish_time):
    """The same reliability transition for committed and privately projected rides."""
    lift.apply_journey_wear()
    lift.operating_time_since_failure_sec += max(0.0, float(operating_seconds or 0.0))
    health_factor = max(0.1, min(1.0, float(lift.health_percent or 0.0) / 100.0))
    mtbf = max(0.0, float(lift.mean_time_between_failures_hours or 0.0)) * 3600.0 * health_factor
    if mtbf <= 0 or lift.operating_time_since_failure_sec < mtbf:
        return
    repair = max(0.0, float(lift.mean_time_to_repair_hours or 0.0)) * 3600.0
    lift.failed_until = max(float(lift.available_time), float(finish_time or lift.available_time)) + repair
    lift.available_time = max(lift.available_time, lift.failed_until)
    lift.failures_count += 1
    lift.operating_time_since_failure_sec = 0.0


def projected_lift(lift, journeys):
    previous = [leg for leg in journeys if leg['lift'].id == lift.id]
    if not previous:
        return lift
    result = copy(lift)
    # A projection must never journal writes into a live commit transaction.
    result.__dict__.pop('_reservation_journal', None)
    for leg in previous:
        result.available_time = max(result.available_time, leg['lift_finish'])
        result.current_floor = leg['destination_lift'].floor
        advance_lift_wear(result, leg.get('reposition_sec', 0.0) + leg.get('loaded_travel_sec', 0.0), leg['lift_finish'])
    return result


def structural_route_possible(sim, amr, start, finish, payload, rules):
    """Physical reachability, independent of temporary outages and bookings."""
    from amr_sim_payload_instances import is_empty_payload_name
    via = required_waypoint(sim.config, start.floor, finish.floor)
    orientations = {orientation for slot in sim._runtime_amr_payload_slots(amr)
                    for orientation in sim._compatible_payload_orientations(payload, slot)}
    if is_empty_payload_name(payload.name):
        orientations = {'lengthways'}
    for orientation in orientations:
        width = sim._required_corridor_width(amr, payload, orientation)
        # Direct travel bypasses the conditional transfer floor. Mandatory
        # waypoints remain independent hard constraints.
        if via is None or via == finish.floor:
            for lift in sim.lifts:
                if not lift.can_serve(start.floor, finish.floor) or not sim._lift_allowed(lift, rules):
                    continue
                if sim._lift_health_speed_factor(lift) <= 0 or not lift.can_fit(payload, amr, orientation):
                    continue
                origin = sim._lift_location_on_floor(lift, start.floor)
                end = sim._lift_location_on_floor(lift, finish.floor)
                if (sim._shortest_path_same_floor(start.floor, start.name, origin.name,
                        rules=rules, minimum_width_m=width) is not None
                    and sim._shortest_path_same_floor(finish.floor, end.name, finish.name,
                        rules=rules, minimum_width_m=width) is not None):
                    return True
        effective_via = via if via is not None else sim.config.get('building', {}).get('lift_transfer_floor')
        pending = [(start, effective_via is None or start.floor == effective_via, frozenset({start.floor}))]
        seen = set()
        while pending:
            current, visited, used_floors = pending.pop()
            key = current.name, visited, used_floors
            if key in seen:
                continue
            seen.add(key)
            if current.floor == finish.floor and visited and sim._shortest_path_same_floor(
                    current.floor, current.name, finish.name, rules=rules, minimum_width_m=width) is not None:
                return True
            for lift in sim.lifts:
                if (current.floor not in lift.served_floors or not sim._lift_allowed(lift, rules)
                        or sim._lift_health_speed_factor(lift) <= 0
                        or not lift.can_fit(payload, amr, orientation=orientation)):
                    continue
                origin = sim._lift_location_on_floor(lift, current.floor)
                if not sim._node_allowed(origin.name, rules) or sim._shortest_path_same_floor(
                        current.floor, current.name, origin.name, rules=rules, minimum_width_m=width) is None:
                    continue
                for floor in lift.served_floors:
                    if floor in used_floors:
                        continue
                    destination = sim._lift_location_on_floor(lift, floor)
                    if sim._node_allowed(destination.name, rules):
                        pending.append((destination, visited or floor == effective_via, used_floors | {floor}))
    return False


def lift_plan_segments(sim, plan, amr, payload, start_time, *, reserve=False,
                       reserve_corridors=True):
    """Materialise and optionally book all rides; energy belongs to each ride."""
    from amr_sim_energy import total_lift_energy_kwh, energy_for_travel_kwh, loaded_power_w, idle_move_power_w
    from amr_sim_payload_instances import is_empty_payload_name
    segments = []
    energy = distance = empty_seconds = loaded_seconds = 0.0
    time = start_time
    for leg in lift_plan_journeys(plan):
        lift = leg['lift']
        origin, destination = leg['origin_lift'], leg['destination_lift']
        leg_energy = total_lift_energy_kwh(
            lift=lift, payload=payload, floor_height_m=sim.floor_height_m,
            reposition_floor_delta=leg['reposition_to_floor'] - leg['reposition_from_floor'],
            loaded_floor_delta=destination.floor - origin.floor,
            wait_time_sec=leg['wait_time'], door_time_sec=lift.door_time_sec,
            boarding_time_sec=lift.boarding_time_sec,
            entry_time_sec=leg.get('entry_time_sec'), exit_time_sec=leg.get('exit_time_sec'))
        energy += leg_energy
        empty_seconds += leg.get('reposition_sec', 0.0)
        loaded_seconds += leg.get('loaded_travel_sec', 0.0)
        connector_distance = sum((leg.get(key) or {}).get('distance_m', 0.0) for key in ('entry_edge', 'exit_edge'))
        distance += leg['to_lift_distance_m'] + leg['vertical_distance_m'] + leg['from_lift_distance_m'] + connector_distance
        if reserve:
            if reserve_corridors:
                sim._reserve_corridor_segments(amr, leg['to_lift_segments'], time)
                sim._reserve_corridor_segments(amr, leg['from_lift_segments'], leg['lift_finish'])
                for key, start in (('entry_edge', leg['entry_start_sec']),
                                   ('exit_edge', leg['loaded_finish'] + lift.door_time_sec)):
                    edge = leg.get(key)
                    if edge:
                        duration = leg['entry_time_sec' if key == 'entry_edge' else 'exit_time_sec']
                        sim._reserve_corridor_segments(amr, [dict(edge, type='corridor', duration=duration)], start)
            sim._reserve_lift_wait_node(leg, amr)
            sim._reserve_lift_journey(leg, amr.id)
            sim._apply_lift_journey_wear(lift,
                journey_operating_sec=leg.get('reposition_sec', 0.0) + leg.get('loaded_travel_sec', 0.0),
                journey_finish_time=leg['lift_finish'])
        segments.extend(leg['to_lift_segments'])
        if leg['wait_time'] > 0:
            segments.append(dict(type='wait_for_lift', lift_id=lift.id,
                **{'from': leg['lift_wait_node'], 'to': leg['lift_wait_node']},
                duration=leg['wait_time'], distance_m=0.0))
        if leg.get('reposition_sec', 0.0) > 0:
            reposition_distance = abs(leg['reposition_to_floor'] - leg['reposition_from_floor']) * sim.floor_height_m
            segments.append(dict(type='lift_reposition', lift_id=lift.id,
                **{'from': f"{lift.id}-F{leg['reposition_from_floor']}",
                   'to': f"{lift.id}-F{leg['reposition_to_floor']}"},
                amr_wait_node=leg['lift_wait_node'], from_floor=leg['reposition_from_floor'],
                to_floor=leg['reposition_to_floor'], wait_time=0.0,
                duration=leg['reposition_sec'], distance_m=reposition_distance,
                vertical_distance_m=reposition_distance, energy_kwh=0.0, energy_source='lift_supply'))
        segments.append(dict(type='lift_transfer', lift_id=lift.id,
            **{'from': origin.name, 'to': destination.name},
            from_floor=origin.floor, to_floor=destination.floor, wait_time=0.0,
            duration=max(0.0, leg['lift_finish'] - leg['reposition_finish']),
            distance_m=leg['vertical_distance_m'] + connector_distance, vertical_distance_m=leg['vertical_distance_m'],
            energy_kwh=leg_energy, energy_source='lift_supply',
            entry_start_sec=leg['entry_start_sec'], entry_time_sec=leg['entry_time_sec'],
            exit_time_sec=leg['exit_time_sec'], door_time_sec=lift.door_time_sec,
            lift_selection_reason=leg.get('lift_selection_reason', 'earliest_completion'),
            destination_walking_distance_m=leg['destination_walking_distance_m'],
            entry_edge=leg.get('entry_edge'), exit_edge=leg.get('exit_edge')))
        if 'required_floor' in leg:
            segments[-1].update(required_floor=leg['required_floor'],
                                required_floor_visited=leg['required_floor_visited'])
        for key in ('bed_fallback_reason', 'bed_fallback_lift_ids', 'predicted_fm_wait_sec',
                    'estimated_time_saved_sec', 'bed_fallback_wait_limit_sec', 'bed_fallback_decision', 'bed_fallback_start_sec'):
            if key in leg:
                segments[-1][key] = leg[key]
        if leg.get('entry_edge'):
            power = idle_move_power_w(amr) if is_empty_payload_name(payload.name) else loaded_power_w(amr, payload)
            segments[-1]['amr_transfer_energy_kwh'] = energy_for_travel_kwh(
                power, leg['entry_time_sec'] + leg['exit_time_sec'])
        segments.extend(leg['from_lift_segments'])
        time = leg['final_finish']
    return segments, energy, distance, empty_seconds, loaded_seconds
