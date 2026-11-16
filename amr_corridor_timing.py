"""Time a prepared Simple corridor against the run's current reservations."""

from math import isfinite
import os

from amr_sim_payload_instances import is_empty_payload_name


try:
    if os.environ.get('AMR_DISABLE_NATIVE_CORRIDOR') == '1':
        _native_corridor = None
    else:
        import _amr_corridor_native as _native_corridor
except (ImportError, OSError):
    _native_corridor = None


class CorridorTiming:
    """Keep static path preparation separate from read-only timing.

    The caller keeps reservations stable for each route evaluation. Prepared
    edges are reusable, while every evaluation reads the current bookings.
    """
    PATH_CACHE_LIMIT = 2048

    def __init__(self, simulation):
        self.sim = simulation
        self.paths = {}
        kernel = _native_corridor
        self._native_evaluate = None
        self.native_used = False
        self.native_path = None
        if (kernel is not None and hasattr(kernel, 'evaluate')
                and all(isfinite(value) for value in (
                    simulation.edge_congestion_window_sec, simulation.edge_slowdown_per_amr,
                    simulation.min_congestion_speed_factor))):
            self._native_evaluate = kernel.evaluate
            self.native_path = kernel.__file__

    def prepare(self, route, amr, payload, orientation, speed):
        loaded_length = loaded_width = 0.0
        if payload is not None and not is_empty_payload_name(payload.name):
            loaded_length, loaded_width, _ = self.sim._payload_orientation_dimensions(payload, orientation)
        length = max(float(amr.length_m or 0.0), loaded_length)
        width = max(float(amr.width_m or 0.0), loaded_width)
        label = orientation if payload is not None else ''
        key = (id(route), speed, length, width, label)
        cached = self.paths.get(key)
        if cached is not None:
            return cached[1]

        prepared = []
        sim = self.sim
        for edge in route['edges']:
            origin, destination = edge['from'], edge['to']
            directed = (origin, destination)
            physical = sim._physical_edge_key(origin, destination)
            lane_count, lane_width, carrying_length = sim._corridor_lane_capacity(edge, amr, payload, orientation)
            corridor_width = edge.get('width_m', sim.default_corridor_width_m)
            template = {
                'type': 'corridor', 'from': origin, 'to': destination,
                'duration': 0.0, 'distance_m': edge['distance_m'],
                'speed_factor': 1.0, 'congestion_count': 0,
                'people_count': 0, 'people_groups': '', 'people_speed_factor': 1.0,
                'people_delay_sec': 0.0, 'scenario_name': '', 'scenario_reason': '',
                'scenario_delay_sec': 0.0, 'route_lane_count': lane_count,
                'corridor_width_m': float(corridor_width),
                'configured_corridor_width_m': float(edge.get('configured_width_m', corridor_width)),
                'door_restricted': bool(edge.get('door_restricted', False)),
                'door_nodes': ','.join(edge.get('door_nodes', []) or []),
                'lane_width_m': lane_width, 'carrying_length_m': carrying_length,
                'payload_orientation': label,
            }
            prepared.append((origin, destination, directed, physical,
                             float(edge['distance_m']) / speed, lane_count, template))
        if len(self.paths) >= self.PATH_CACHE_LIMIT:
            self.paths.clear()
        # Keep the route alive so its identity cannot be reused by another path.
        self.paths[key] = route, prepared
        return prepared

    def evaluate(self, route, amr, payload, orientation, current, collect_segments):
        speed = max(float(amr.speed_m_per_sec), 1e-9)
        path = self.prepare(route, amr, payload, orientation, speed)
        sim = self.sim
        spacing = sim._spacing_time_sec(amr)
        if self._native_evaluate is None:
            result = self.time_path(path, current, spacing, collect_segments)
        else:
            self.native_used = True
            result = self._native_evaluate(
                path, sim.edge_reservations, sim.directed_edge_reservations,
                sim.node_reservations, sim.edge_reservation_max_duration,
                sim.directed_edge_reservation_max_duration, sim.node_reservation_max_duration,
                current, spacing, sim.edge_congestion_window_sec, sim.edge_slowdown_per_amr,
                sim.min_congestion_speed_factor, collect_segments)
        if result is not None:
            return *result, route['distance_m']
        return None

    def time_path(self, path, current, spacing, collect_segments):
        """Evaluate ordered edges without writing reservations or segment templates."""
        sim = self.sim
        demand = sim._edge_recent_demand
        edge_start_at = sim._find_next_edge_start
        node_arrival_at = sim._find_next_node_arrival
        min_factor = sim.min_congestion_speed_factor
        slowdown = sim.edge_slowdown_per_amr
        minimum_active = max(.01, min(min_factor, 1.0))
        segments = []
        total = 0.0

        for origin, destination, directed, physical, base, lanes, template in path:
            if not isfinite(current):
                return None
            recent = demand(physical, current)
            congestion = max(min_factor, 1.0 - recent * slowdown)
            factor = max(.01, min(congestion, 1.0))
            travel_time = base / factor
            edge_start, _ = edge_start_at(physical, current, travel_time, spacing, directed, lanes)
            edge_wait = max(0.0, edge_start - current)
            if edge_wait > 0:
                if collect_segments:
                    segments.append({'type': 'wait_for_edge', 'from': origin, 'to': origin,
                                     'duration': edge_wait, 'distance_m': 0.0,
                                     'congestion_count': recent, 'route_lane_count': lanes})
                total += edge_wait
                current = edge_start

            proposed = current + travel_time
            safe = node_arrival_at(destination, proposed, spacing)
            node_wait = max(0.0, safe - proposed)
            duration = travel_time
            if node_wait > 0:
                # Absorb a node conflict by slowing along the edge where safe.
                adjusted = travel_time + node_wait
                effective = base / max(adjusted, 1e-9)
                if effective >= minimum_active:
                    duration = adjusted
                    factor = min(factor, effective)
                else:
                    duration = base / minimum_active
                    stop_wait = max(0.0, safe - (current + duration))
                    if stop_wait > 0:
                        if collect_segments:
                            segments.append({'type': 'wait_for_node', 'from': origin, 'to': origin,
                                             'blocked_node': destination, 'duration': stop_wait,
                                             'distance_m': 0.0, 'congestion_count': recent,
                                             'route_lane_count': lanes})
                        total += stop_wait
                        current += stop_wait
                    factor = minimum_active

            if collect_segments:
                segment = template.copy()
                segment.update(duration=duration, speed_factor=factor, congestion_count=recent)
                segments.append(segment)
            total += duration
            current += duration
        return segments, total
