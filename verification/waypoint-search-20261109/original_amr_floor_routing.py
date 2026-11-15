"""Floor waypoint policy and read-only planning of connecting lift journeys."""
import heapq
import itertools
import math
from copy import copy


def required_waypoint(config, start_floor, end_floor):
    if start_floor == end_floor:
        return None
    for rule in config.get('building', {}).get('mandatory_floor_waypoints', []):
        if rule['from_floor'] == start_floor and end_floor in rule['to_floors']:
            return rule['via_floor']
    return None


def lift_policy_key(config):
    building = config.get('building', {})
    return (building.get('lift_transfer_floor'), tuple(building.get('destination_side_lift_floors', [])),
            tuple((r['from_floor'], tuple(r['to_floors']), r['via_floor'])
                  for r in building.get('mandatory_floor_waypoints', [])))


def destination_direct_plan(sim, ready_time, amr, start, finish, payload, rules,
                            orientation, collect_segments, prior_journeys=()):
    """Choose by destination walking distance only on explicitly selected floors."""
    floors = sim.config.get('building', {}).get('destination_side_lift_floors', [])
    direct = sim._direct_lift_plan
    if start.floor not in floors:
        return direct(ready_time, amr, start, finish, payload, rules, orientation,
                      collect_segments, prior_journeys=prior_journeys)
    winner = None
    winner_key = None
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


def connecting_lift_plan(sim, ready_time, amr, start, finish, payload, rules,
                         orientation, collect_segments):
    """Search lift landings without mutating shared bookings during estimates.

    A landing is an actual alighting/boarding stop, not a floor passed inside
    a moving car. Every edge uses the existing horizontal/width/profile and
    lift scheduling checks. Earlier rides form a private booking overlay.
    """
    via = required_waypoint(sim.config, start.floor, finish.floor)
    direct = sim._direct_lift_plan
    if via is None or via == finish.floor:
        plan = destination_direct_plan(sim, ready_time, amr, start, finish, payload, rules,
                                       orientation, collect_segments)
        if plan is not None:
            return plan
    building = sim.config.get('building', {})
    if via is None:
        via = building.get('lift_transfer_floor')
    policy_enabled = (building.get('lift_transfer_floor') is not None
                      or bool(building.get('destination_side_lift_floors')))
    serial = itertools.count()
    queue = [(ready_time, next(serial), start, via is None or via == start.floor, ())]
    best = {}
    winner = None
    while queue:
        time, _, current, visited, journeys = heapq.heappop(queue)
        if winner is not None and time >= winner['final_finish']:
            break
        # Do not invent lift up/down loops as a substitute for a missing
        # corridor connection. Real connecting routes visit each floor once.
        used_floors = frozenset([start.floor] + [leg['destination_lift'].floor for leg in journeys])
        key = (current.name, visited, used_floors)
        if time >= best.get(key, math.inf):
            continue
        best[key] = time
        if visited and policy_enabled and finish.floor not in used_floors:
            final = destination_direct_plan(sim, time, amr, current, finish, payload, rules,
                                            orientation, collect_segments, journeys)
            if final is not None:
                if winner is None or final['final_finish'] < winner['final_finish']:
                    winner = dict(journeys=journeys + (final,), final_finish=final['final_finish'])
                # A suitable direct final ride takes priority over extra connections.
                continue
        for lift in sim.lifts:
            if current.floor not in lift.served_floors or not sim._lift_allowed(lift, rules):
                continue
            for floor in lift.served_floors:
                if floor in used_floors:
                    continue
                satisfied = visited or floor == via
                final_leg = floor == finish.floor and satisfied
                target = finish if final_leg else sim._lift_location_on_floor(lift, floor)
                next_key = (target.name, satisfied, used_floors | {floor})
                if not final_leg and time >= best.get(next_key, math.inf):
                    continue
                leg = direct(time, amr, current, target, payload, rules, orientation,
                             collect_segments, only_lift=lift.id, prior_journeys=journeys)
                if leg is None:
                    continue
                target = leg.get('routing_end_location', target)
                next_key = (target.name, satisfied, used_floors | {floor})
                path = journeys + (leg,)
                if final_leg:
                    if winner is None or leg['final_finish'] < winner['final_finish']:
                        winner = dict(journeys=path, final_finish=leg['final_finish'])
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
        if leg.get('entry_edge'):
            power = idle_move_power_w(amr) if is_empty_payload_name(payload.name) else loaded_power_w(amr, payload)
            segments[-1]['amr_transfer_energy_kwh'] = energy_for_travel_kwh(
                power, leg['entry_time_sec'] + leg['exit_time_sec'])
        segments.extend(leg['from_lift_segments'])
        time = leg['final_finish']
    return segments, energy, distance, empty_seconds, loaded_seconds
