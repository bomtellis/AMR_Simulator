"""Opt-in mandatory-floor AMR journeys, including same-floor round trips.

Legacy routing stays in amr_floor_routing. A visit here means a completed lift
ride and alighting, never passing the floor inside a car.
"""
import heapq
import itertools
import math
from collections import deque


FALLBACK_SEARCH_STATES = 32
LIFT_LEG_CACHE_LIMIT = 4096
SHARED_LIFT_LEG_CACHE_LIMIT = 16384
REACHABILITY_CACHE_LIMIT = 8192


def enabled(config):
    return config.get('building', {}).get('force_via_floor_enabled', False) is True


def lift_preference_key(config):
    if not enabled(config):
        return ()
    preference = config['building'].get('forced_floor_lift_preference', {})
    mode = preference.get('mode', 'off')
    if mode == 'off':
        return ()
    return mode, preference['from_floor'], tuple(sorted(preference['lift_ids']))


def lift_preference(config, start_floor, profile_applied=False):
    if not enabled(config) or profile_applied:
        return 'off', None
    preference = config['building'].get('forced_floor_lift_preference', {})
    mode = preference.get('mode', 'off')
    if mode == 'off' or preference['from_floor'] != start_floor:
        return 'off', None
    return mode, frozenset(preference['lift_ids'])


def lift_allowed_at_required_floor(lift_id, origin, destination, via, selected):
    return (selected is None or (origin != via and destination != via)
            or lift_id in selected)


def requires_lift_route(config, start, finish):
    if not enabled(config) or start.name == finish.name:
        return False
    via = config['building']['force_via_floor']
    return start.floor != finish.floor or start.floor != via


def _usable(sim, lift, amr, payload, rules, orientation):
    return (sim._lift_allowed(lift, rules) and sim._lift_health_speed_factor(lift) > 0
            and lift.can_fit(payload, amr, orientation=orientation))


def _reachable(sim, amr, start, finish, payload, rules, orientation, final_lift=None,
               selected=None):
    """Physical reachability using the same landing/visit states as execution."""
    via = sim.config['building']['force_via_floor']
    width = sim._required_corridor_width(amr, payload, orientation)
    lifts = [lift for lift in sim.lifts if _usable(sim, lift, amr, payload, rules, orientation)]
    cache = getattr(sim, '_forced_reachability_cache', None)
    if (cache is None or sim.scenario_mode or sim.geometric_motion or sim.parallel_routing_enabled
            or any(getattr(lift, 'transfer_timing_mode', 'fixed') != 'fixed' for lift in lifts)):
        return _search_reachability(sim, amr, start, finish, payload, rules, orientation,
                                    final_lift, selected, via, width, lifts)

    # The graph is owned by this run. Refresh lift eligibility for the current
    # payload, robot, permissions and operational health on every query.
    key = (start.floor, start.name, finish.floor, finish.name, via, width,
           sim._rules_cache_key(rules), tuple(lift.id for lift in lifts),
           final_lift.id if final_lift is not None else None,
           frozenset(selected) if selected is not None else None)
    cached = cache.get(key)
    if cached is not None:
        sim._check_run_cancelled()
        return cached

    result = _search_reachability(sim, amr, start, finish, payload, rules, orientation,
                                  final_lift, selected, via, width, lifts)
    if len(cache) >= REACHABILITY_CACHE_LIMIT:
        cache.clear()
    cache[key] = result
    return result


def _search_reachability(sim, amr, start, finish, payload, rules, orientation,
                         final_lift, selected, via, width, lifts):
    pending = deque([(start, start.floor == via)])
    seen = set()

    def walk(a, b):
        return (sim._node_allowed(a.name, rules) and sim._node_allowed(b.name, rules)
                and sim._shortest_path_same_floor(a.floor, a.name, b.name,
                    rules=rules, minimum_width_m=width) is not None)

    while pending:
        sim._check_run_cancelled()
        current, visited = pending.popleft()
        key = current.name, visited
        if key in seen:
            continue
        seen.add(key)
        if final_lift is None and visited and current.floor == finish.floor and walk(current, finish):
            return True
        for lift in lifts:
            if current.floor not in lift.served_floors:
                continue
            origin = sim._lift_location_on_floor(lift, current.floor)
            if not walk(current, origin):
                continue
            for floor in lift.served_floors:
                if floor == current.floor:
                    continue
                if not lift_allowed_at_required_floor(lift.id, current.floor, floor, via, selected):
                    continue
                destination = sim._lift_location_on_floor(lift, floor)
                if not sim._node_allowed(destination.name, rules):
                    continue
                satisfied = visited or floor == via
                if ((final_lift is None or lift.id == final_lift.id) and satisfied
                        and floor == finish.floor and walk(destination, finish)):
                    if getattr(lift, 'transfer_timing_mode', 'fixed') != 'speed_based':
                        return True
                    from amr_lift_transfer import graph_transfer_connectors
                    if graph_transfer_connectors(sim, amr, current, finish,
                            origin, destination, payload, rules, orientation) is not None:
                        return True
                # Speed-based intermediate journeys finish outside the car.
                if getattr(lift, 'transfer_timing_mode', 'fixed') == 'speed_based':
                    from amr_lift_transfer import graph_transfer_connectors
                    links = graph_transfer_connectors(sim, amr, current, destination,
                        origin, destination, payload, rules, orientation)
                    if links is None:
                        continue
                    destination = sim.graph_nodes[links[1]['to']]
                pending.append((destination, satisfied))
    return False


def structural_route_possible(sim, amr, start, finish, payload, rules):
    from amr_sim_payload_instances import is_empty_payload_name
    orientations = {orientation for slot in sim._runtime_amr_payload_slots(amr)
                    for orientation in sim._compatible_payload_orientations(payload, slot)}
    if is_empty_payload_name(payload.name):
        orientations = {'lengthways'}
    mode, selected = lift_preference(sim.config, start.floor, (rules or {}).get('profile_applied', False))
    # Fallback admits every structurally valid forced-floor route.
    if mode != 'required':
        selected = None
    return any(_reachable(sim, amr, start, finish, payload, rules, orientation, selected=selected)
               for orientation in orientations)


def forced_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                     orientation, collect_segments, *, finish_before=math.inf):
    mode, selected = lift_preference(sim.config, start.floor, (rules or {}).get('profile_applied', False))
    fallback = (rules or {}).get('bed_fallback_search', False)
    if fallback and mode != 'required':
        selected = None
    result = _search_forced_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                                     orientation, collect_segments, selected, finish_before,
                                     quick=fallback)
    if result is None and fallback and finish_before == math.inf and not sim.stop_requested:
        return _search_forced_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                                        orientation, collect_segments, selected, finish_before,
                                        first_feasible=True)
    if result is None and selected is not None and mode == 'prefer' and not sim.stop_requested:
        return _search_forced_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                                        orientation, collect_segments, None, finish_before)
    return result


def _search_forced_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                             orientation, collect_segments, selected, finish_before, *,
                             quick=False, first_feasible=False):
    """Plan a forced stop, with a bounded wait comparison for fallback.

    Each search owns its corridor cache and private lift booking overlay. A
    landing may be revisited after the required stop; different landings on
    the same floor remain available on either side of it.
    """
    from amr_bed_lifts import access_intervals, boarding_wait
    from amr_floor_routing import minimum_lift_journey_seconds, optimistic_remaining_times, projected_lift
    from amr_route_reservations import latest_lift_reservation
    via = sim.config['building']['force_via_floor']
    available_from = {}
    usable_lifts = []
    for lift in sim.lifts:
        sim._check_run_cancelled()
        if not _usable(sim, lift, amr, payload, rules, orientation):
            continue
        # Reliability-sensitive bookings append after the committed tail.
        # Other lifts can still fit a journey into a compatible gap.
        reservations = sim.lift_reservations.get(lift.id, ())
        earliest = max(ready_time, lift.failed_until)
        if not reservations:
            earliest = max(earliest, lift.available_time)
        elif lift.health_loss_per_journey_percent > 0 or lift.mean_time_between_failures_hours > 0:
            earliest = max(earliest, latest_lift_reservation(reservations)[1])
        if lift.usage_mode == 'bed_fallback':
            window = next(access_intervals(sim, lift, earliest), (math.inf, math.inf))
            earliest = max(earliest, window[0])
        if (quick or first_feasible) and earliest >= finish_before:
            continue
        usable_lifts.append(lift)
        available_from[lift.id] = earliest

    width = sim._required_corridor_width(amr, payload, orientation)
    candidates = []
    for lift in usable_lifts:
        if finish.floor not in lift.served_floors:
            continue
        landing = sim._lift_location_on_floor(lift, finish.floor)
        if not sim._node_allowed(landing.name, rules):
            continue
        walking = sim._shortest_path_same_floor(finish.floor, landing.name, finish.name,
            rules=rules, minimum_width_m=width)
        if walking is not None:
            candidates.append((walking['distance_m'], str(lift.id), lift))
    if quick or first_feasible:
        candidates.sort(key=lambda item: (available_from[item[2].id], *item[:2]))
    else:
        candidates.sort(key=lambda item: (item[0], available_from[item[2].id], item[1]))
    stops = getattr(sim, '_lift_landings', None)
    connections = getattr(sim, '_lift_connections', {})
    if (stops is None or sim.scenario_mode or sim.geometric_motion
            or any(lift.id not in connections for lift in usable_lifts)):
        stops = {(lift.id, floor): sim._lift_location_on_floor(lift, floor)
                 for lift in usable_lifts for floor in lift.served_floors}
        connections = {lift.id: tuple((floor, stops[lift.id, floor]) for floor in lift.served_floors)
                       for lift in usable_lifts}
    free_flow = None
    if not (sim.scenario_mode or sim.geometric_motion or sim.parallel_routing_enabled):
        free_flow = getattr(sim, '_free_flow_lift_distances', None)
    speed = max(float(amr.speed_m_per_sec), 1e-9)
    reachable = {}
    route_cache = {} if not sim.scenario_mode and not sim.geometric_motion else None
    leg_cache = {} if route_cache is not None else None
    cache_limit = LIFT_LEG_CACHE_LIMIT
    batch = getattr(sim, '_forced_lift_estimate_batch', None)
    if batch is not None:
        # Legacy corridor timing and lift fit depend on the robot's dimensions
        # and speeds. A read-only batch holds the same committed reservations.
        key = (sim._rules_cache_key(rules), sim._payload_cache_key(payload), orientation,
               collect_segments, amr.speed_m_per_sec, amr.length_m, amr.width_m, amr.height_m,
               amr.lift_entry_speed_m_per_sec, amr.lift_exit_speed_m_per_sec)
        if key in batch or len(batch) < 16:
            route_cache, leg_cache = batch.setdefault(key, ({}, {}))
            cache_limit = SHARED_LIFT_LEG_CACHE_LIMIT
    winner = winner_key = None

    def wait_key(journeys, wait):
        return (wait, journeys[-1]['final_finish'], tuple(leg['lift'].id for leg in journeys),
                tuple((leg['origin_lift'].floor, leg['destination_lift'].floor) for leg in journeys))

    def direct(time, current, target, lift, journeys, cutoff, *, prior=None):
        opening = available_from[lift.id]
        if sim.stop_requested or not math.isfinite(opening) or max(time, opening) > cutoff:
            return None
        if not lift_allowed_at_required_floor(lift.id, current.floor, target.floor, via, selected):
            return None
        # Only this car's private rides affect its projected position, wear
        # and booking slots. Reuse identical legs across final-car searches.
        if prior is None:
            prior = tuple(leg for leg in journeys if leg['lift'].id == lift.id)
        if leg_cache is not None:
            key = (time, current.name, target.name, lift.id, tuple(
                (leg['lift_start'], leg['lift_finish'], leg['origin_lift'].floor,
                 leg['destination_lift'].floor, leg['reposition_sec'], leg['loaded_travel_sec'])
                for leg in prior))
            if key in leg_cache:
                return leg_cache[key]
        if free_flow and math.isfinite(cutoff) and lift.transfer_timing_mode == 'fixed':
            origin_stop = stops.get((lift.id, current.floor))
            target_stop = stops.get((lift.id, target.floor))
            if origin_stop is None or target_stop is None:
                return None
            incoming = free_flow.get((current.floor, current.name, origin_stop.name), 0.0)
            outgoing = free_flow.get((target.floor, target_stop.name, target.name), 0.0)
            earliest = (max(time + incoming / speed, opening)
                        + minimum_lift_journey_seconds(lift, current.floor, target.floor)
                        + outgoing / speed)
            # Ignore congestion and repositioning, and allow for the different
            # floating-point addition order in the exact route. A cutoff miss
            # must not enter the shared leg cache as an unavailable route.
            slack = 1e-8 * max(1.0, abs(time), abs(cutoff))
            if earliest > cutoff + slack:
                return None
        plan = sim._direct_lift_plan(time, amr, current, target, payload, rules,
            orientation, collect_segments, only_lift=lift.id,
            prior_journeys=prior, _route_cache=route_cache)
        if leg_cache is not None and len(leg_cache) < cache_limit:
            leg_cache[key] = plan
        return plan

    def seed(final_lift, cutoff):
        """Evaluate the direct and two-ride routes before searching detours."""
        best = ()
        best_key = None
        if start.floor == via or finish.floor == via:
            if final_lift.can_serve(start.floor, finish.floor) and start.floor != finish.floor:
                leg = direct(ready_time, start, finish, final_lift, (), cutoff)
                if leg is not None and leg['final_finish'] <= cutoff:
                    best = (leg,)
        elif via in final_lift.served_floors and lift_allowed_at_required_floor(
                final_lift.id, via, finish.floor, via, selected):
            for first in usable_lifts:
                sim._check_run_cancelled()
                if not first.can_serve(start.floor, via):
                    continue
                landing = stops[first.id, via]
                leg = direct(ready_time, start, landing, first, (), cutoff)
                if leg is None:
                    continue
                current = leg.get('routing_end_location', landing)
                last = direct(leg['final_finish'], current, finish, final_lift, (leg,), cutoff)
                if last is None or last['final_finish'] > cutoff:
                    continue
                if quick and last['final_finish'] >= finish_before:
                    continue
                key = (wait_key((leg, last), boarding_wait(leg) + boarding_wait(last))
                       if quick else (last['final_finish'],))
                if best_key is None or key < best_key:
                    best = leg, last
                    best_key = key
                    if not quick:
                        cutoff = last['final_finish']
        return best

    def connecting_seed(final_lift, cutoff):
        # A single car can serve the required stop and take the robot onward
        # to a floor where it can board the destination car.
        best = ()
        if via in (start.floor, finish.floor):
            return best
        for first in usable_lifts:
            sim._check_run_cancelled()
            if not first.can_serve(start.floor, via):
                continue
            via_landing = stops[first.id, via]
            inbound = direct(ready_time, start, via_landing, first, (), cutoff)
            if inbound is None:
                continue
            current = inbound.get('routing_end_location', via_landing)
            for floor in first.served_floors:
                if floor in (via, finish.floor) or floor not in final_lift.served_floors:
                    continue
                landing = stops[first.id, floor]
                onward = direct(inbound['final_finish'], current, landing, first, (inbound,), cutoff)
                if onward is None:
                    continue
                current_landing = onward.get('routing_end_location', landing)
                last = direct(onward['final_finish'], current_landing, finish, final_lift,
                              (inbound, onward), cutoff)
                if last is not None and last['final_finish'] <= cutoff and (
                        not best or last['final_finish'] < best[-1]['final_finish']):
                    best = inbound, onward, last
                    cutoff = last['final_finish']
        return best

    def annotate(plan, reason):
        visited = start.floor == via
        annotated = []
        for index, leg in enumerate(plan):
            visited = visited or leg['destination_lift'].floor == via
            selection = reason if index == len(plan) - 1 else 'mandatory_floor_connection'
            value = dict(leg, required_floor=via, required_floor_visited=visited, lift_selection_reason=selection)
            if batch is not None and collect_segments:
                # Task estimates annotate these segments with energy and handling information.
                for key in ('to_lift_segments', 'from_lift_segments'):
                    value[key] = [dict(segment) for segment in leg[key]]
            annotated.append(value)
        return dict(journeys=tuple(annotated), final_finish=plan[-1]['final_finish'], required_floor=via)

    if quick:
        if not candidates:
            return None
        best = ()
        best_key = (math.inf, finish_before, (), ())
        for _, _, lift in candidates:
            sim._check_run_cancelled()
            plan = seed(lift, finish_before)
            if plan and plan[-1]['final_finish'] < finish_before:
                key = wait_key(plan, sum(map(boarding_wait, plan)))
                if key < best_key:
                    best, best_key = plan, key

        # All final cars share the same prefixes. The budget now counts unique
        # prefix expansions across the comparison. Each expansion checks all
        # compatible final cars and can open further multi-floor connections.
        final_options = tuple((lift, distance) for distance, _, lift in candidates)
        allowed = frozenset(available_from)
        deadline = None
        if math.isfinite(finish_before):
            deadline = finish_before + 1e-8 * max(1.0, abs(ready_time), abs(finish_before))
        bounds = optimistic_remaining_times(sim, amr, finish, via, allowed_lifts=allowed,
            required_floor_lifts=selected, finish_by=deadline, lift_openings=available_from,
            final_options=final_options)
        if bounds is None:
            bounds = {}
            unreachable = 0.0
        else:
            unreachable = math.inf
        slack = deadline - finish_before if deadline is not None else 0.0
        terminal_by_floor = {}
        for _, _, lift in candidates:
            for floor in lift.served_floors:
                if floor != finish.floor and lift_allowed_at_required_floor(lift.id, floor, finish.floor, via, selected):
                    terminal_by_floor.setdefault(floor, []).append(lift)
        next_stops = {}
        for lift in usable_lifts:
            for origin in lift.served_floors:
                for floor, target in connections[lift.id]:
                    if floor == origin or not lift_allowed_at_required_floor(lift.id, origin, floor, via, selected):
                        continue
                    duration = minimum_lift_journey_seconds(lift, origin, floor)
                    before = bounds.get((target.name, target.floor == via), unreachable)
                    after = bounds.get((target.name, True), unreachable)
                    if lift.transfer_timing_mode != 'fixed':
                        before = after = 0.0
                    next_stops.setdefault(origin, []).append(
                        (lift, target, available_from[lift.id], duration, before, after))

        serial = itertools.count()
        visited = start.floor == via
        used = frozenset({(start.name, visited)})
        queue = [(0.0, ready_time + bounds.get((start.name, visited), unreachable),
                  next(serial), ready_time, start, visited, (), used)]
        states_left = FALLBACK_SEARCH_STATES
        if sim.progress_callback and not sim.parallel_routing_enabled:
            sim._print_progress('Planning lift routes')
        while queue and states_left:
            sim._check_run_cancelled()
            if sim.stop_requested:
                return None
            wait, optimistic, _, time, current, visited, journeys, used = heapq.heappop(queue)
            states_left -= 1
            if wait > best_key[0]:
                break
            if time >= finish_before:
                continue
            cutoff = min(finish_before, best_key[1]) if wait == best_key[0] else finish_before
            if not math.isfinite(optimistic) or optimistic > cutoff + slack:
                continue
            prior_by_lift = {}
            for leg in journeys:
                prior_by_lift.setdefault(leg['lift'].id, []).append(leg)
            if visited or finish.floor == via:
                for lift in terminal_by_floor.get(current.floor, ()):
                    leg = direct(time, current, finish, lift, journeys, cutoff,
                                 prior=prior_by_lift.get(lift.id, ()))
                    if leg is None or leg['final_finish'] >= finish_before:
                        continue
                    plan = journeys + (leg,)
                    key = wait_key(plan, wait + boarding_wait(leg))
                    if key < best_key:
                        best, best_key = plan, key
            if not states_left:
                break
            cutoff = min(finish_before, best_key[1]) if wait == best_key[0] else finish_before
            children = []
            for lift, target, opening, duration, before, after in next_stops.get(current.floor, ()):
                satisfied = visited or target.floor == via
                state = target.name, satisfied
                if state in used:
                    continue
                # A landing on the destination floor can still connect to
                # another car. The terminal walk is checked separately above.
                optimistic_finish = max(time, opening) + duration + (after if visited else before)
                if optimistic_finish > cutoff + slack:
                    continue
                leg = direct(time, current, target, lift, journeys, cutoff,
                             prior=prior_by_lift.get(lift.id, ()))
                if leg is None:
                    continue
                end = leg.get('routing_end_location', target)
                state = end.name, satisfied
                if state in used:
                    continue
                new_wait = wait + boarding_wait(leg)
                estimate = leg['final_finish'] + bounds.get(state, unreachable)
                if new_wait > best_key[0] or not math.isfinite(estimate) or estimate > cutoff + slack:
                    continue
                if new_wait == best_key[0] and estimate > best_key[1] + slack:
                    continue
                children.append((new_wait, estimate, next(serial), leg['final_finish'], end,
                                 satisfied, journeys + (leg,), used | {state}))
            queue = heapq.nsmallest(states_left, itertools.chain(queue, children))
        return annotate(best, 'least_predicted_lift_wait') if best else None

    # A path cannot alight at the same physical landing in the same phase
    # twice. Bound the total number of private rides conservatively by all
    # graph nodes in both phases, plus its final arrival. Reliability counters
    # are immaterial only when even this worst case cannot cause a failure.
    max_rides = 2 * len(sim.graph_nodes) + 1
    counter_matters = {}
    for lift in usable_lifts:
        minimum_health = max(.1, (lift.health_percent - max_rides * lift.health_loss_per_journey_percent) / 100)
        threshold = lift.mean_time_between_failures_hours * 3600 * minimum_health
        span = max(lift.served_floors) - min(lift.served_floors)
        maximum_operating = max_rides * 2 * span / (
            lift.speed_floors_per_sec * max(.05, min(1.0, lift.health_speed_penalty_at_zero or .5)))
        counter_matters[lift.id] = bool(sim.scenario_mode or threshold > 0 and
            lift.operating_time_since_failure_sec + maximum_operating >= threshold)

    def remaining(node, visited):
        return 0.0 if bounds is None else bounds.get((node.name, visited), math.inf)

    for distance, lift_id, final_lift in candidates:
        sim._check_run_cancelled()
        if winner_key is not None and distance > winner_key[0]:
            break
        if sim.stop_requested:
            return None
        search_limit = finish_before
        if winner is not None:
            search_limit = min(search_limit, winner['final_finish'])
        opening = available_from.get(final_lift.id, ready_time)
        if opening >= finish_before or opening > search_limit:
            continue
        if lift_id not in reachable:
            reachable[lift_id] = _reachable(sim, amr, start, finish, payload, rules,
                                            orientation, final_lift, selected)
        if not reachable[lift_id]:
            continue
        # Distance is the primary selection criterion. Once the sole nearest
        # reachable car has a complete valid route, extra detours cannot change
        # its selection. Only equal-distance cars need completion-time search.
        compare_times = False
        if not first_feasible:
            for other_distance, other_id, other in candidates:
                if other_distance != distance or other_id == lift_id:
                    continue
                if other_id not in reachable:
                    reachable[other_id] = _reachable(sim, amr, start, finish, payload, rules,
                                                      orientation, other, selected)
                compare_times |= reachable[other_id]
        allowed_lifts = frozenset(lift_id for lift_id, opening in available_from.items()
                                  if math.isfinite(opening) and opening <= search_limit)
        bounds = optimistic_remaining_times(sim, amr, finish, via, final_lift, distance,
            allowed_lifts=allowed_lifts, required_floor_lifts=selected)
        best_plan = seed(final_lift, search_limit)
        best_finish = best_plan[-1]['final_finish'] if best_plan else math.inf
        if best_finish > search_limit or best_finish >= finish_before:
            best_plan, best_finish = None, math.inf
        if bounds is not None and best_plan is None:
            connection = connecting_seed(final_lift, search_limit)
            if connection:
                search_limit = connection[-1]['final_finish']
                if not compare_times:
                    best_plan, best_finish = connection, search_limit

        def accept(journeys, leg):
            nonlocal best_plan, best_finish
            if leg is None or leg['final_finish'] >= min(best_finish, finish_before) or leg['final_finish'] > search_limit:
                return
            best_plan, best_finish = journeys + (leg,), leg['final_finish']

        serial = itertools.count()
        visited = start.floor == via
        used = frozenset({(start.name, visited)})
        queue = [(ready_time + remaining(start, visited), next(serial), ready_time,
                  start, visited, (), used)]
        labels = {}
        deadline = math.inf
        timed_bounds = None
        while queue and (compare_times or best_plan is None):
            sim._check_run_cancelled()
            if sim.progress_callback and not sim.parallel_routing_enabled:
                sim._print_progress('Planning lift routes')
            optimistic, _, time, current, visited, journeys, used = heapq.heappop(queue)
            if sim.stop_requested:
                return None
            cutoff = min(best_finish, search_limit)
            slack = 1e-8 * max(1.0, abs(time), abs(cutoff) if math.isfinite(cutoff) else 1.0)
            if not math.isfinite(optimistic) or optimistic > cutoff + slack:
                break
            if time >= best_finish or time >= finish_before or time > search_limit:
                continue
            if bounds is not None and cutoff < deadline:
                deadline = cutoff
                timed_bounds = optimistic_remaining_times(sim, amr, finish, via, final_lift, distance,
                    allowed_lifts=allowed_lifts, required_floor_lifts=selected,
                    finish_by=deadline + slack, lift_openings=available_from)
            if timed_bounds is not None and time + timed_bounds.get((current.name, visited), math.inf) > cutoff + slack:
                continue
            # Only merge labels with equivalent future lift state. Completed
            # private bookings are in the past, but their final floors, wear
            # and repairs still change the next journey. Do not let an earlier
            # arrival with a differently positioned car suppress a valid route.
            fleet = []
            for actual in usable_lifts:
                projected = projected_lift(actual, journeys)
                fleet.append((projected.current_floor, projected.health_percent,
                    projected.failed_until,
                    projected.available_time if projected.available_time > time else 0,
                    projected.operating_time_since_failure_sec if counter_matters[actual.id] else 0))
            context = current.name, visited, tuple(fleet)
            existing = labels.setdefault(context, [])
            if any(prior_time <= time and prior_used <= used for prior_time, prior_used in existing):
                continue
            existing[:] = [(prior_time, prior_used) for prior_time, prior_used in existing
                           if not (time <= prior_time and used <= prior_used)]
            existing.append((time, used))
            if (visited or finish.floor == via) and current.floor != finish.floor:
                if final_lift.can_serve(current.floor, finish.floor):
                    accept(journeys, direct(time, current, finish, final_lift, journeys, cutoff))
                    if best_plan is not None and not compare_times:
                        break
            for lift in usable_lifts:
                if current.floor not in lift.served_floors:
                    continue
                for floor, target in connections[lift.id]:
                    if floor == current.floor:
                        continue
                    if not lift_allowed_at_required_floor(lift.id, current.floor, floor, via, selected):
                        continue
                    satisfied = visited or floor == via
                    if (target.name, satisfied) in used:
                        continue
                    # This actual final ride was evaluated against the exact
                    # endpoint above; there is no need to expand beyond it.
                    if lift.id == final_lift.id and floor == finish.floor and satisfied:
                        continue
                    if bounds is not None and lift.transfer_timing_mode == 'fixed':
                        future = timed_bounds if timed_bounds is not None else bounds
                        remaining_time = future.get((target.name, satisfied), math.inf)
                        earliest = (max(time, available_from[lift.id])
                                    + minimum_lift_journey_seconds(lift, current.floor, floor))
                        if not math.isfinite(remaining_time) or earliest + remaining_time > cutoff + slack:
                            continue
                    leg = direct(time, current, target, lift, journeys, cutoff)
                    if leg is None:
                        continue
                    target = leg.get('routing_end_location', target)
                    state = target.name, satisfied
                    if state in used:
                        continue
                    estimate = leg['final_finish'] + remaining(target, satisfied)
                    if estimate > min(best_finish, search_limit) + slack:
                        continue
                    heapq.heappush(queue, (estimate, next(serial), leg['final_finish'], target,
                                          satisfied, journeys + (leg,), used | {state}))
        if best_plan is not None:
            key = (distance, best_finish, lift_id)
            if winner_key is None or key < winner_key:
                reason = 'mandatory_floor_connection' if first_feasible else 'nearest_reachable_destination_stop'
                winner = annotate(best_plan, reason)
                winner_key = key
                if first_feasible:
                    break
    return winner
