"""Time-dependent Simple routes; queries never reserve or commit travel."""
import heapq
import math
from datetime import datetime, timedelta


def segment_state(sim, amr, edge, requested):
    """Wait through every overlapping outage before resolving effective speed."""
    ready = float(requested)
    resources = [('corridor', f"{edge['from']} -> {edge['to']}"),
                 ('corridor_node', edge['from']), ('corridor_node', edge['to']), ('amr', amr.id)]
    notes = ''
    limit = ready + 8 * 86400
    origin = sim.clock.sim_seconds_to_datetime(0)
    for event in sim.scenario_events:
        if event.get('end_datetime'):
            limit = max(limit, (datetime.fromisoformat(event['end_datetime']) - origin).total_seconds() + 8 * 86400)
    while True:
        states = [sim._resource_speed_factor(kind, identity, ready) for kind, identity in resources]
        notes = next((note for _, _, note in states if note), notes)
        blocked = [end for factor, end, _ in states if factor <= 0]
        if not blocked:
            return ready, min(factor for factor, _, _ in states), notes
        following = max(blocked)
        if following <= ready or following > limit:
            return math.inf, 0.0, notes
        ready = following


def departure_state(sim, amr, edge, requested, base_duration):
    """Allow waiting for a slowdown to end as well as waiting for closures.

    Taking the minimum over departures makes the scenario edge cost FIFO: a
    robot arriving earlier can always choose the departure of a later arrival.
    """
    if not sim.scenario_mode:
        return float(requested), 1.0, ''
    candidates = {float(requested)}
    origin = sim.clock.sim_seconds_to_datetime(0)
    day = sim.clock.sim_seconds_to_datetime(requested)
    resources = [('corridor', f"{edge['from']} -> {edge['to']}"),
                 ('corridor_node', edge['from']), ('corridor_node', edge['to']), ('amr', amr.id)]
    for event in sim.scenario_events:
        kind = event.get('resource_type')
        ids = event.get('resource_ids') or [event.get('resource_id', '')]
        if isinstance(ids, str):
            ids = [value.strip() for value in ids.split(',')]
        if not any(kind == resource and any(sim._scenario_resource_matches(kind, identity, candidate)
                   for identity in ids) for resource, candidate in resources):
            continue
        for offset in range(-1, 8):
            window = sim._scenario_window(event, day + timedelta(days=offset))
            if window:
                end = (window[1] - origin).total_seconds()
                if end > requested:
                    candidates.add(end)
            if event.get('end_datetime'):
                break
    options = [segment_state(sim, amr, edge, candidate) for candidate in sorted(candidates)]
    return min(options, key=lambda state: (state[0] + base_duration / max(.01, state[1]), state[0]))


def earliest_route(sim, amr, start, end, rules, width, requested, payload, orientation):
    """Find earliest predicted arrival on permitted directed corridor edges."""
    graph = sim.floor_graphs.get(start.floor, {})
    rules = rules or sim._empty_route_rules()
    if start.name not in graph or end.name not in graph:
        return None
    if not sim._node_allowed(start.name, rules) or not sim._node_allowed(end.name, rules):
        return None
    intermediate_lifts = sim.lift_stop_names - {start.name, end.name}
    best = {start.name: float(requested)}
    previous = {}
    queue = [(float(requested), start.name)]
    while queue:
        arrival, node = heapq.heappop(queue)
        if arrival > best[node]:
            continue
        if node == end.name:
            break
        for raw in sorted(graph[node], key=lambda e: e['to']):
            nxt = raw['to']
            if (nxt in intermediate_lifts or raw['width_m'] + 1e-9 < width
                    or not sim._node_allowed(nxt, rules) or not sim._edge_allowed(node, nxt, rules)):
                continue
            edge = {**raw, 'from': node, 'to': nxt}
            base = edge['distance_m'] / max(amr.speed_m_per_sec, 1e-9)
            ready, factor, _ = departure_state(sim, amr, edge, arrival, base)
            if not math.isfinite(ready):
                continue
            key = sim._physical_edge_key(node, nxt)
            congestion = max(sim.min_congestion_speed_factor,
                             1 - sim._edge_recent_demand(key, ready) * sim.edge_slowdown_per_amr)
            _, people, _ = sim._people_on_edge(key, ready, base)
            duration = base / max(.01, min(factor, congestion, people))
            lanes, _, _ = sim._corridor_lane_capacity(edge, amr, payload, orientation)
            entry, _ = sim._find_next_edge_start(edge_key=key, requested_start=ready, duration=duration,
                spacing_time=sim._spacing_time_sec(amr), directed_edge_key=(node, nxt), max_concurrency=lanes)
            # Reservations can move entry into another event window.
            while entry > ready + 1e-9:
                ready, factor, _ = departure_state(sim, amr, edge, entry, base)
                if not math.isfinite(ready):
                    break
                _, people, _ = sim._people_on_edge(key, ready, base)
                duration = base / max(.01, min(factor, congestion, people))
                entry, _ = sim._find_next_edge_start(edge_key=key, requested_start=ready, duration=duration,
                    spacing_time=sim._spacing_time_sec(amr), directed_edge_key=(node, nxt), max_concurrency=lanes)
            if not math.isfinite(ready):
                continue
            finish = sim._find_next_node_arrival(nxt, entry + duration, sim._spacing_time_sec(amr))
            if finish < best.get(nxt, math.inf):
                best[nxt] = finish
                previous[nxt] = (node, edge)
                heapq.heappush(queue, (finish, nxt))
    if end.name not in best:
        return None
    edges = []
    node = end.name
    while node != start.name:
        node, edge = previous[node]
        edges.append(edge)
    edges.reverse()
    return {'edges': edges, 'distance_m': sum(edge['distance_m'] for edge in edges)}
