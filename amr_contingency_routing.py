"""Human/trolley graph routing with private lift-booking overlays during trials."""
from copy import deepcopy
import heapq
import itertools
import math

from amr_floor_routing import required_waypoint
from amr_route_reservations import LiftReservations
from amr_contingency_packing import lift_rectangles,pack_lift


class NoHumanRoute(ValueError):
    pass


class HumanRouter:
    def __init__(self, sim):
        self.sim = sim
        self.bookings = {lift.id: [] for lift in sim.lifts}
        self.landing = {f'{lift.id}-F{floor}': (lift, floor)
                        for lift in sim.lifts for floor in lift.served_floors}
        self.no_routes = set()
        self.allowed_graphs = {}
        self.walking_trees = {}
        self.route_previews = {}

    def walking_tree(self,graph_key,origin):
        """Static corridor distances only; lift queues never enter this cache."""
        key=(graph_key,origin)
        if key not in self.walking_trees:
            distances={origin:0.0};previous={};serial=itertools.count()
            queue=[(0.0,next(serial),origin)]
            graph=self.allowed_graphs[graph_key]
            while queue:
                distance,_,node=heapq.heappop(queue)
                if distance>distances[node]:continue
                for edge in graph.get(node,[]):
                    end=edge['to'];candidate=distance+edge['distance_m']
                    if candidate<distances.get(end,math.inf):
                        distances[end]=candidate;previous[end]=(node,edge['distance_m'])
                        heapq.heappush(queue,(candidate,next(serial),end))
            self.walking_trees[key]=(distances,previous)
        return self.walking_trees[key]

    def ride(self, lift, origin, destination, ready, profile, bookings, rectangles):
        fit=lambda items:pack_lift(lift.capacity_length_m,lift.capacity_width_m,lift.capacity_height_m,items)
        packing=fit(rectangles)
        if packing is None:return None
        rows = bookings[lift.id]
        # Side-by-side units, with full length/height clearance, share a departure.
        for index, row in enumerate(rows):
            if row['origin'] == origin and row['destination'] == destination and ready+lift.boarding_time_sec <= row['depart']:
                combined=row['rectangles']+rectangles
                shared_packing=fit(combined)
                if shared_packing is not None:
                    return dict(row,index=index,rectangles=combined,packing=shared_packing,shared=True,
                                wait=max(0.0,row['board']-ready))
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
                    finish=finish, rectangles=rectangles,packing=packing,shared=False,index=len(rows),
                    wait=max(0.0, board-ready))

    def route(self, origin, destination, ready, profile, tasks, factor, bookings):
        # Insertion trials repeatedly ask for identical journey prefixes. Keep
        # only previews with identical time, load, permissions and queue state.
        rules=self.sim._onboard_route_rules(tasks)
        permissions=tuple(sorted((key,tuple(sorted(values))) for key,values in (rules or {}).items()))
        lift_state=tuple((lift.id,lift.available_time,lift.current_floor,lift.failed_until,
                          tuple(self.sim.lift_reservations.get(lift.id,()))) for lift in self.sim.lifts)
        key=(id(bookings),origin,destination,ready,profile['width_m'],profile.get('route_profile'),
             profile['loaded_speed_mps'] if tasks else profile['empty_speed_mps'],factor,
             permissions,lift_rectangles(self.sim.payloads,profile,tasks),lift_state)
        if key in self.route_previews:return self.route_previews[key][1]
        result=self._route(origin,destination,ready,profile,tasks,factor,bookings)
        if len(self.route_previews)>=1024:self.route_previews.clear()
        # Retain the input object so its identity cannot be reused by another
        # speculative booking map while the cached entry is alive.
        self.route_previews[key]=(bookings,result)
        return result

    def _route(self, origin, destination, ready, profile, tasks, factor, bookings):
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
        permissions = tuple(sorted((key, tuple(sorted(values))) for key,values in (rules or {}).items()))
        graph_key = (profile['width_m'], permissions)
        rectangles=lift_rectangles(sim.payloads,profile,tasks)
        route_key = (origin,destination,profile['width_m'],rectangles,permissions)
        if route_key in self.no_routes:
            raise NoHumanRoute(f'No permitted route or lift capacity: {origin} → {destination}.')
        if graph_key not in self.allowed_graphs:
            self.allowed_graphs[graph_key] = {
                node: [edge for edge in edges if profile['width_m'] <= edge['width_m']+1e-9
                       and sim._node_allowed(edge['to'], rules) and sim._edge_allowed(node, edge['to'], rules)]
                for floor in sim.floor_graphs.values() for node,edges in floor.items()}
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
            distances,previous=self.walking_tree(graph_key,node)
            # Only the destination and lift landings can change the next routing
            # decision. Retain every corridor leg when expanding a cached path.
            targets=[destination]+[name for name,(_,level) in self.landing.items() if level==floor]
            for end in dict.fromkeys(targets):
                if end==node or end not in distances:continue
                arrival=now+distances[end]/speed*factor
                if arrival>=best.get((end,seen or floor==via),math.inf):continue
                path=[];cursor=end
                while cursor!=node:
                    parent,distance=previous[cursor];path.append((parent,cursor,distance));cursor=parent
                time=now;walks=[]
                for origin_node,end_node,distance in reversed(path):
                    duration=distance/speed*factor
                    walks.append(dict(action='walk',start=time,end=time+duration,origin=origin_node,
                        destination=end_node,distance_m=distance,wait_seconds=0.0))
                    time+=duration
                heapq.heappush(queue,(time,next(serial),end,seen or floor==via,legs+walks,overlay))
            if node in self.landing:
                lift, origin_floor = self.landing[node]
                if not sim._lift_allowed(lift, rules):
                    continue
                for end_floor in lift.served_floors:
                    end = f'{lift.id}-F{end_floor}'
                    if end_floor == origin_floor or not sim._node_allowed(end, rules):
                        continue
                    ride = self.ride(lift, origin_floor, end_floor, now, profile, overlay,rectangles)
                    if ride is None:
                        continue
                    changed = {k:list(v) for k,v in overlay.items()}
                    if ride['shared']:
                        changed[lift.id][ride['index']] = ride
                    else:
                        changed[lift.id].append(ride)
                    leg = dict(action='lift', start=now, end=ride['finish'], origin=node, destination=end,
                               distance_m=abs(end_floor-origin_floor)*sim.floor_height_m,
                               wait_seconds=ride['wait'], lift=lift.id,
                               lift_arrangement='; '.join(f"{ride['rectangles'][i][4]} at ({x:g}, {y:g}) m: {l:g} × {w:g} m"
                                   +(' rotated' if turned else '') for i,x,y,l,w,turned in ride['packing']))
                    heapq.heappush(queue, (ride['finish'], next(serial), end, seen or end_floor == via, legs+[leg], changed))
        # Only immutable connectivity/capacity failures are cached. Successful
        # routes always evaluate current lift queues and reservations afresh.
        self.no_routes.add(route_key)
        raise NoHumanRoute(f'No permitted route or lift capacity: {origin} → {destination}.')

    def commit(self, bookings):
        self.route_previews.clear()
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
