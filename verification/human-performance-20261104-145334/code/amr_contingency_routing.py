"""Human/trolley graph routing with private lift-booking overlays during trials."""
from copy import deepcopy
import heapq
import itertools
import math

from amr_floor_routing import required_waypoint
from amr_route_reservations import LiftReservations


class NoHumanRoute(ValueError):
    pass


class HumanRouter:
    def __init__(self, sim):
        self.sim = sim
        self.bookings = {lift.id: [] for lift in sim.lifts}
        self.landing = {f'{lift.id}-F{floor}': (lift, floor)
                        for lift in sim.lifts for floor in lift.served_floors}

    def ride(self, lift, origin, destination, ready, profile, bookings):
        # A profile describes the complete person + carrying-unit envelope.
        if any(profile[k] > getattr(lift, 'capacity_'+k)+1e-9 for k in ('length_m', 'width_m', 'height_m')):
            return None
        rows = bookings[lift.id]
        # Side-by-side units, with full length/height clearance, share a departure.
        for index, row in enumerate(rows):
            if (row['origin'] == origin and row['destination'] == destination and ready+lift.boarding_time_sec <= row['depart']
                    and row['used_width']+profile['width_m'] <= lift.capacity_width_m+1e-9):
                return dict(row, index=index, used_width=row['used_width']+profile['width_m'], shared=True,
                            wait=max(0.0, row['board']-ready))
        last = max(rows, key=lambda r:r['finish'], default=None)
        # Preserve any existing booked lift use in the simulator's reservation store.
        native = self.sim.lift_reservations.get(lift.id, [])
        latest = max(native, key=lambda r:r[1], default=None)
        available = max(ready, last['finish'] if last else lift.available_time,
                        latest[1] if latest else 0, lift.failed_until)
        floor = last['destination'] if last else lift.current_floor
        if latest and (not last or latest[1] > last['finish']):
            floor = latest[3]
        board = available + lift.vertical_travel_duration_sec(origin-floor, self.sim.floor_height_m)
        depart = board + lift.door_time_sec + lift.boarding_time_sec
        finish = (depart + lift.vertical_travel_duration_sec(destination-origin, self.sim.floor_height_m)
                  + lift.door_time_sec + lift.boarding_time_sec)
        return dict(origin=origin, destination=destination, board=board, depart=depart,
                    finish=finish, used_width=profile['width_m'], shared=False, index=len(rows),
                    wait=max(0.0, board-ready))

    def route(self, origin, destination, ready, profile, tasks, factor, bookings):
        sim = self.sim
        if origin not in sim.graph_nodes or destination not in sim.graph_nodes:
            raise NoHumanRoute(f'Missing route endpoint: {origin} → {destination}.')
        if origin == destination:
            return ready, [], bookings
        rules = sim._onboard_route_rules(tasks)
        override = profile.get('route_profile')
        if override is not None:
            from amr_sim_models import Task
            rules = sim._resolve_task_route_rules(Task('human-routing', origin, destination, '', route_profile=override))
        via = required_waypoint(sim.config, sim.graph_nodes[origin].floor, sim.graph_nodes[destination].floor)
        serial = itertools.count()
        visited = via is None or sim.graph_nodes[origin].floor == via
        queue = [(ready, next(serial), origin, visited, [], bookings)]
        best = {}
        speed = profile['loaded_speed_mps'] if tasks else profile['empty_speed_mps']
        while queue:
            now, _, node, seen, legs, overlay = heapq.heappop(queue)
            key = (node, seen)
            if now >= best.get(key, math.inf):
                continue
            best[key] = now
            if node == destination and seen:
                return now, legs, overlay
            floor = sim.graph_nodes[node].floor
            for edge in sim.floor_graphs.get(floor, {}).get(node, []):
                end = edge['to']
                if (profile['width_m'] > edge['width_m']+1e-9 or
                    not sim._node_allowed(end, rules) or not sim._edge_allowed(node, end, rules)):
                    continue
                duration = edge['distance_m']/speed*factor
                leg = dict(action='walk', start=now, end=now+duration, origin=node, destination=end,
                           distance_m=edge['distance_m'], wait_seconds=0.0)
                heapq.heappush(queue, (now+duration, next(serial), end, seen or floor == via, legs+[leg], overlay))
            if node in self.landing:
                lift, origin_floor = self.landing[node]
                if not sim._lift_allowed(lift, rules):
                    continue
                for end_floor in lift.served_floors:
                    end = f'{lift.id}-F{end_floor}'
                    if end_floor == origin_floor or not sim._node_allowed(end, rules):
                        continue
                    ride = self.ride(lift, origin_floor, end_floor, now, profile, overlay)
                    if ride is None:
                        continue
                    changed = {k:list(v) for k,v in overlay.items()}
                    if ride['shared']:
                        changed[lift.id][ride['index']] = ride
                    else:
                        changed[lift.id].append(ride)
                    leg = dict(action='lift', start=now, end=ride['finish'], origin=node, destination=end,
                               distance_m=abs(end_floor-origin_floor)*sim.floor_height_m,
                               wait_seconds=ride['wait'], lift=lift.id)
                    heapq.heappush(queue, (ride['finish'], next(serial), end, seen or end_floor == via, legs+[leg], changed))
        raise NoHumanRoute(f'No permitted route or lift capacity: {origin} → {destination}.')

    def commit(self, bookings):
        self.bookings = bookings
        # Keep the native reservation history auditable. Only add new rides.
        for lift_id, rows in bookings.items():
            native = self.sim.lift_reservations.setdefault(lift_id, LiftReservations())
            known = {(r[0], r[1], r[2], r[3]) for r in native}
            for row in rows:
                value = (row['board'], row['finish'], row['origin'], row['destination'])
                if value not in known:
                    native.append(value)
                    known.add(value)
