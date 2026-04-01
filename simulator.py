import argparse
import csv
import heapq
import json
import math
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from amr_sim_energy import requires_recharge_before_route, total_route_energy_kwh
from amr_sim_models import AMR, Event, Lift, Location, PayloadType, Task
from amr_sim_time_utils import (
    SimulationClock,
    format_duration,
    parse_datetime,
    parse_release_time,
)


class Simulation:
    def __init__(
        self,
        config: dict,
        verbose: bool = False,
        verbose_csv_path: Optional[str] = None,
    ):
        self.location_reservations = defaultdict(list)
        sim_cfg = config.get("simulation", {})
        start_datetime = parse_datetime(
            sim_cfg.get("start_datetime", "2026-01-01T08:00:00")
        )
        tick_rate = float(sim_cfg.get("tick_rate", 120.0))

        self.clock = SimulationClock(start_datetime=start_datetime, tick_rate=tick_rate)
        self.current_time = 0.0
        self.verbose = verbose
        self.verbose_csv_path = verbose_csv_path
        self.verbose_rows: List[dict] = []
        self.event_counter = 0
        self.events: List[Event] = []
        self.pending_tasks: List[Tuple[int, float, int, Task]] = []
        self.pending_task_counter = 0
        self.lock = threading.RLock()
        self.stop_requested = False
        self.completed_task_records: List[dict] = []
        self.failed_tasks: List[dict] = []
        self.location_reservations: Dict[str, List[Tuple[float, float]]] = defaultdict(
            list
        )

        self.load_unload_time_sec = float(
            config["building"].get("load_unload_time_sec", 20.0)
        )
        self.floor_height_m = float(config["building"].get("floor_height_m", 4.0))
        self.charge_location_name = config["building"].get(
            "charge_location", config["locations"][0]["name"]
        )

        # Parse locations from config

        self.locations: Dict[str, Location] = {
            loc["name"]: Location(
                name=loc["name"],
                floor=int(loc["floor"]),
                x=float(loc.get("x", 0.0)),
                y=float(loc.get("y", 0.0)),
            )
            for loc in config["locations"]
        }

        # Parse maximum concurrency from config

        self.location_max_concurrency: Dict[str, int] = {
            loc["name"]: int(loc.get("max_concurrency", 999999))
            for loc in config["locations"]
        }

        # Parse payloads from configuration

        self.payloads: Dict[str, PayloadType] = {
            p["name"]: PayloadType(
                name=p["name"],
                weight_kg=float(p["weight_kg"]),
                size_units=float(p.get("size_units", 1.0)),
            )
            for p in config["payloads"]
        }

        self.route_profiles = config.get("route_profiles", {})

        # Parse lifts from configuration

        self.lifts: List[Lift] = []
        for item in config["lifts"]:
            floor_locations = {
                int(floor): (float(coords["x"]), float(coords["y"]))
                for floor, coords in item.get("floor_locations", {}).items()
            }

            lift = Lift(
                id=item["id"],
                served_floors=list(item["served_floors"]),
                speed_floors_per_sec=float(item["speed_floors_per_sec"]),
                door_time_sec=float(item.get("door_time_sec", 4.0)),
                boarding_time_sec=float(item.get("boarding_time_sec", 5.0)),
                floor_locations=floor_locations,
                capacity_size_units=float(item.get("capacity_size_units", 1.0)),
                current_floor=int(item.get("start_floor", 0)),
            )

            for floor in lift.served_floors:
                if floor not in lift.floor_locations:
                    raise ValueError(
                        f"Lift {lift.id} is missing floor_locations for floor {floor}"
                    )

            self.lifts.append(lift)

        self.graph_nodes: Dict[str, Location] = {}
        self.floor_graphs: Dict[int, Dict[str, List[dict]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._build_floor_graphs(config.get("corridors", {}))

        # Parse AMRS from configuration

        self.amrs: List[AMR] = []
        for amr_type in config["amrs"]:
            quantity = int(amr_type.get("quantity", 1))
            for i in range(quantity):
                self.amrs.append(
                    AMR(
                        id=f"{amr_type['id']}-{i + 1}",
                        payload_capacity_kg=float(amr_type["payload_capacity_kg"]),
                        payload_size_capacity=float(
                            amr_type.get("payload_size_capacity", 1.0)
                        ),
                        speed_m_per_sec=float(amr_type["speed_m_per_sec"]),
                        motor_power_w=float(amr_type.get("motor_power_w", 750.0)),
                        battery_capacity_kwh=float(
                            amr_type.get("battery_capacity_kwh", 5.0)
                        ),
                        battery_charge_rate_kw=float(
                            amr_type.get("battery_charge_rate_kw", 1.5)
                        ),
                        recharge_threshold_percent=float(
                            amr_type.get("recharge_threshold_percent", 20.0)
                        ),
                        battery_soc_percent=float(
                            amr_type.get("battery_soc_percent", 100.0)
                        ),
                        location_name=amr_type.get(
                            "start_location", config["locations"][0]["name"]
                        ),
                        is_charging=False,
                    )
                )

        # Parse tasks from configuration

        initial_tasks = []
        for task_dict in config.get("tasks", []):
            task_data = dict(task_dict)
            task_data["release_time"] = parse_release_time(
                task_data, self.clock.start_datetime
            )
            task_data.pop("release_datetime", None)
            initial_tasks.append(Task(**task_data))

        for task in initial_tasks:
            self.schedule_task_release(task)

    def _empty_route_rules(self) -> dict:
        return {
            "allowed_lifts": set(),
            "allowed_nodes": set(),
            "allowed_edges": set(),
        }

    def _edge_key(self, a_name: str, b_name: str) -> Tuple[str, str]:
        return (a_name, b_name)

    def _resolve_task_route_rules(self, task: Task) -> dict:
        rules = self._empty_route_rules()

        profile_name = getattr(task, "route_profile", None)
        if not profile_name and "dirty" in getattr(task, "labels", []):
            profile_name = "dirty"

        if profile_name:
            profile = self.route_profiles.get(profile_name, {})
            rules["allowed_lifts"].update(profile.get("allowed_lifts", []))
            rules["allowed_nodes"].update(profile.get("allowed_nodes", []))
            rules["allowed_edges"].update(
                self._edge_key(a, b) for a, b in profile.get("allowed_edges", [])
            )

        rules["allowed_lifts"].update(getattr(task, "allowed_lifts", []))
        rules["allowed_nodes"].update(getattr(task, "allowed_nodes", []))
        rules["allowed_edges"].update(
            self._edge_key(a, b) for a, b in getattr(task, "allowed_edges", [])
        )

        return rules

    def _node_allowed(self, node_name: str, rules: Optional[dict]) -> bool:
        if not rules:
            return True
        allowed_nodes = rules.get("allowed_nodes", set())
        if not allowed_nodes:
            return True
        return node_name in allowed_nodes

    def _edge_allowed(
        self, from_name: str, to_name: str, rules: Optional[dict]
    ) -> bool:
        if not rules:
            return True
        allowed_edges = rules.get("allowed_edges", set())
        if not allowed_edges:
            return True
        return (from_name, to_name) in allowed_edges

    def _lift_allowed(self, lift: Lift, rules: Optional[dict]) -> bool:
        if not rules:
            return True
        allowed_lifts = rules.get("allowed_lifts", set())
        if not allowed_lifts:
            return True
        return lift.id in allowed_lifts

    def _build_floor_graphs(self, corridor_cfg: dict):
        for location in self.locations.values():
            self.graph_nodes[location.name] = location
            self.floor_graphs[location.floor][location.name]

        for lift in self.lifts:
            for floor in lift.served_floors:
                node = lift.location_on_floor(floor)
                self.graph_nodes[node.name] = node
                self.floor_graphs[floor][node.name]

        for node_data in corridor_cfg.get("nodes", []):
            node = Location(
                name=node_data["name"],
                floor=int(node_data["floor"]),
                x=float(node_data["x"]),
                y=float(node_data["y"]),
            )
            self.graph_nodes[node.name] = node
            self.floor_graphs[node.floor][node.name]

        def add_edge(
            a_name: str,
            b_name: str,
            distance_m: Optional[float] = None,
            bidirectional: bool = True,
        ):
            if a_name not in self.graph_nodes or b_name not in self.graph_nodes:
                raise ValueError(
                    f"Corridor edge references unknown node: {a_name} -> {b_name}"
                )
            a = self.graph_nodes[a_name]
            b = self.graph_nodes[b_name]
            if a.floor != b.floor:
                raise ValueError(
                    f"Same-floor graph edge crosses floors: {a_name} -> {b_name}"
                )
            dist = (
                distance_m
                if distance_m is not None
                else self._distance_same_floor(a, b)
            )
            self.floor_graphs[a.floor][a_name].append(
                {"to": b_name, "distance_m": dist}
            )
            if bidirectional:
                self.floor_graphs[b.floor][b_name].append(
                    {"to": a_name, "distance_m": dist}
                )

        for edge in corridor_cfg.get("edges", []):
            add_edge(
                edge["from"],
                edge["to"],
                edge.get("distance_m"),
                edge.get("bidirectional", True),
            )

        # Optional: connect locations/lifts to nearby graph nodes when explicit edges are not supplied
        auto_connect = corridor_cfg.get("auto_connect", True)
        if auto_connect:
            for floor, nodes in self.floor_graphs.items():
                existing_names = list(nodes.keys())
                corridor_names = [
                    name
                    for name in existing_names
                    if name not in self.locations
                    and not name.startswith(tuple(l.id + "-F" for l in self.lifts))
                ]
                if not corridor_names:
                    continue
                for loc in self.locations.values():
                    if loc.floor != floor:
                        continue
                    if nodes[loc.name]:
                        continue
                    nearest = min(
                        corridor_names,
                        key=lambda n: self._distance_same_floor(
                            loc, self.graph_nodes[n]
                        ),
                    )
                    add_edge(loc.name, nearest)
                for lift in self.lifts:
                    lift_name = f"{lift.id}-F{floor}"
                    if lift_name not in nodes or nodes[lift_name]:
                        continue
                    lift_node = self.graph_nodes[lift_name]
                    nearest = min(
                        corridor_names,
                        key=lambda n: self._distance_same_floor(
                            lift_node, self.graph_nodes[n]
                        ),
                    )
                    add_edge(lift_name, nearest)

    def _shortest_path_same_floor(
        self,
        floor: int,
        start_name: str,
        end_name: str,
        rules: Optional[dict] = None,
    ) -> Optional[dict]:
        graph = self.floor_graphs.get(floor, {})
        if start_name not in graph or end_name not in graph:
            return None

        rules = rules or self._empty_route_rules()

        if not self._node_allowed(start_name, rules):
            return None
        if not self._node_allowed(end_name, rules):
            return None

        heap = [(0.0, start_name, [])]
        best = {start_name: 0.0}

        while heap:
            dist, node, path = heapq.heappop(heap)
            if node == end_name:
                return {"distance_m": dist, "edges": path}
            if dist > best.get(node, math.inf):
                continue
            for edge in graph[node]:
                nxt = edge["to"]
                if not self._node_allowed(nxt, rules):
                    continue
                if not self._edge_allowed(node, nxt, rules):
                    continue
                new_dist = dist + edge["distance_m"]
                if new_dist < best.get(nxt, math.inf):
                    best[nxt] = new_dist
                    heapq.heappush(
                        heap,
                        (
                            new_dist,
                            nxt,
                            path
                            + [
                                {
                                    "from": node,
                                    "to": nxt,
                                    "distance_m": edge["distance_m"],
                                }
                            ],
                        ),
                    )
        return None

    def _find_next_available_time(
        self,
        location_name: str,
        requested_start: float,
        duration: float,
    ) -> float:
        max_concurrency = self.location_max_concurrency.get(location_name, 999999)
        reservations = sorted(self.location_reservations[location_name])

        t = requested_start
        while True:
            overlap_count = 0
            next_candidate = None

            for start, end in reservations:
                if not (t + duration <= start or t >= end):
                    overlap_count += 1
                    if next_candidate is None or end < next_candidate:
                        next_candidate = end

            if overlap_count < max_concurrency:
                return t

            if next_candidate is None:
                return t

            t = next_candidate

    def _reserve_location(self, location_name: str, start_time: float, end_time: float):
        self.location_reservations[location_name].append((start_time, end_time))

    def push_event(
        self, time_value: float, event_type: str, payload: Optional[dict] = None
    ):
        self.event_counter += 1
        heapq.heappush(
            self.events,
            Event(
                time=time_value,
                priority=self.event_counter,
                event_type=event_type,
                payload=payload or {},
            ),
        )
        # self.log_step(
        #     event_time=time_value,
        #     event_type="event_scheduled",
        #     details=f"Scheduled event '{event_type}'",
        # )

    def schedule_task_release(self, task: Task):
        self.push_event(task.release_time, "task_release", {"task": task})

    def add_runtime_task(self, task_dict: dict):
        task_data = dict(task_dict)
        task_data["release_time"] = parse_release_time(
            task_data, self.clock.start_datetime
        )
        task_data.pop("release_datetime", None)
        task = Task(**task_data)
        task.created_during_runtime = True
        with self.lock:
            if task.release_time <= self.current_time:
                self._queue_pending_task(task)
                self._try_assign_tasks(self.current_time)
            else:
                self.schedule_task_release(task)

    def _queue_pending_task(self, task: Task):
        self.pending_task_counter += 1
        heapq.heappush(
            self.pending_tasks,
            (task.priority, task.release_time, self.pending_task_counter, task),
        )

    def _distance_same_floor(self, a: Location, b: Location) -> float:
        return math.hypot(b.x - a.x, b.y - a.y)

    def _travel_same_floor(self, amr: AMR, start: Location, end: Location) -> float:
        route = self._shortest_path_same_floor(start.floor, start.name, end.name)
        if route is None:
            return math.inf
        return route["distance_m"] / max(amr.speed_m_per_sec, 1e-9)

    def _same_floor_segments(
        self,
        amr: AMR,
        start: Location,
        end: Location,
        rules: Optional[dict] = None,
    ) -> Optional[Tuple[List[dict], float, float]]:
        route = self._shortest_path_same_floor(
            start.floor,
            start.name,
            end.name,
            rules=rules,
        )
        if route is None:
            return None
        segments = []
        total_duration = 0.0
        for edge in route["edges"]:
            duration = edge["distance_m"] / max(amr.speed_m_per_sec, 1e-9)
            total_duration += duration
            segments.append(
                {
                    "type": "corridor",
                    "from": edge["from"],
                    "to": edge["to"],
                    "duration": duration,
                    "distance_m": edge["distance_m"],
                }
            )
        return segments, total_duration, route["distance_m"]

    def _lift_location_on_floor(self, lift: Lift, floor: int) -> Location:
        return lift.location_on_floor(floor)

    def _nearest_compatible_lift_plan(
        self,
        ready_time: float,
        amr: AMR,
        from_loc: Location,
        to_loc: Location,
        payload: PayloadType,
        rules: Optional[dict] = None,
    ) -> Optional[dict]:
        best_plan = None
        best_finish = math.inf
        rules = rules or self._empty_route_rules()

        for lift in self.lifts:
            if not self._lift_allowed(lift, rules):
                continue
            if not lift.can_serve(from_loc.floor, to_loc.floor):
                continue
            if payload.size_units > lift.capacity_size_units:
                continue

            origin_lift = self._lift_location_on_floor(lift, from_loc.floor)
            destination_lift = self._lift_location_on_floor(lift, to_loc.floor)

            if not self._node_allowed(origin_lift.name, rules):
                continue
            if not self._node_allowed(destination_lift.name, rules):
                continue

            to_lift_route = self._same_floor_segments(
                amr, from_loc, origin_lift, rules=rules
            )
            from_lift_route = self._same_floor_segments(
                amr, destination_lift, to_loc, rules=rules
            )
            if to_lift_route is None or from_lift_route is None:
                continue

            to_lift_segments, to_lift_sec, to_lift_distance_m = to_lift_route
            from_lift_segments, from_lift_sec, from_lift_distance_m = from_lift_route

            arrival_at_lift = ready_time + to_lift_sec
            lift_start = max(arrival_at_lift, lift.available_time)

            reposition = abs(lift.current_floor - from_loc.floor) / max(
                lift.speed_floors_per_sec, 1e-9
            )
            loaded_travel = abs(to_loc.floor - from_loc.floor) / max(
                lift.speed_floors_per_sec, 1e-9
            )

            lift_duration = (
                reposition
                + lift.door_time_sec
                + lift.boarding_time_sec
                + loaded_travel
                + lift.door_time_sec
                + lift.boarding_time_sec
            )

            lift_finish = lift_start + lift_duration
            final_finish = lift_finish + from_lift_sec

            if final_finish < best_finish:
                best_finish = final_finish
                best_plan = {
                    "lift": lift,
                    "origin_lift": origin_lift,
                    "destination_lift": destination_lift,
                    "to_lift_segments": to_lift_segments,
                    "from_lift_segments": from_lift_segments,
                    "to_lift_distance_m": to_lift_distance_m,
                    "from_lift_distance_m": from_lift_distance_m,
                    "to_lift_sec": to_lift_sec,
                    "from_lift_sec": from_lift_sec,
                    "lift_start": lift_start,
                    "lift_finish": lift_finish,
                    "wait_time": max(0.0, (lift_start - arrival_at_lift)),
                    "vertical_distance_m": abs(to_loc.floor - from_loc.floor)
                    * self.floor_height_m,
                    "final_finish": final_finish,
                }

        return best_plan

    def _plan_return_to_charge(
        self,
        amr: AMR,
        current_loc: Location,
        current_time_value: float,
        reserve: bool = False,
    ) -> Optional[dict]:
        charge_loc = self.locations[self.charge_location_name]

        if current_loc.floor == charge_loc.floor:
            route = self._same_floor_segments(amr, current_loc, charge_loc)
            if route is None:
                return None
            segments, travel_sec, distance_m = route
            finish_time = current_time_value + travel_sec

            if reserve:
                amr.location_name = charge_loc.name

            return {
                "segments": segments,
                "travel_sec": travel_sec,
                "distance_m": distance_m,
                "finish_time": finish_time,
                "end_location": charge_loc.name,
            }

        dummy_payload = next(iter(self.payloads.values()))
        plan = self._nearest_compatible_lift_plan(
            current_time_value, amr, current_loc, charge_loc, dummy_payload
        )
        if plan is None:
            return None

        transfer_segments = list(plan["to_lift_segments"])
        transfer_segments.append(
            {
                "type": "lift_transfer",
                "lift_id": plan["lift"].id,
                "from": plan["origin_lift"].name,
                "to": plan["destination_lift"].name,
                "from_floor": current_loc.floor,
                "to_floor": charge_loc.floor,
                "wait_time": plan["wait_time"],
                "duration": plan["lift_finish"] - plan["lift_start"],
                "distance_m": plan["vertical_distance_m"],
                "vertical_distance_m": plan["vertical_distance_m"],
            }
        )
        transfer_segments.extend(plan["from_lift_segments"])

        if reserve:
            plan["lift"].available_time = plan["lift_finish"]
            plan["lift"].current_floor = charge_loc.floor
            amr.location_name = charge_loc.name

        return {
            "segments": transfer_segments,
            "travel_sec": plan["final_finish"] - current_time_value,
            "distance_m": (
                plan["to_lift_distance_m"]
                + plan["vertical_distance_m"]
                + plan["from_lift_distance_m"]
            ),
            "finish_time": plan["final_finish"],
            "end_location": charge_loc.name,
        }

    def _plan_charge_cycle_if_needed(
        self,
        amr: AMR,
        payload: PayloadType,
        to_pickup_sec: float,
        loaded_sec: float,
        ready_time: float,
    ) -> Tuple[float, List[dict], float]:
        required_energy_kwh = total_route_energy_kwh(
            amr, payload, to_pickup_sec, loaded_sec
        )
        extra_segments: List[dict] = []
        adjusted_ready_time = ready_time

        if requires_recharge_before_route(amr, required_energy_kwh):
            charge_duration = amr.charge_duration_sec_to_full()
            extra_segments.append(
                {
                    "type": "charge",
                    "location": amr.location_name,
                    "duration": charge_duration,
                    "battery_soc_before": amr.battery_soc_percent,
                    "battery_soc_after": 100.0,
                }
            )
            adjusted_ready_time += charge_duration

        return adjusted_ready_time, extra_segments, required_energy_kwh

    def _needs_post_task_recharge(self, amr: AMR) -> bool:
        return amr.battery_energy_kwh() < amr.min_reserve_energy_kwh()

    def _create_wait_event_for_pending_tasks(self, now: float):
        if any(e.event_type == "task_wait" and e.time > now for e in self.events):
            return

        if not self.pending_tasks:
            return

        next_times = []

        for amr in self.amrs:
            next_times.append(amr.available_time)

        if self.events:
            next_event_time = min(event.time for event in self.events)
            if next_event_time > now:
                next_times.append(next_event_time)

        future_times = [t for t in next_times if t > now]
        if not future_times:
            return

        wait_until = min(future_times)

        self.push_event(
            wait_until,
            "task_wait",
            {
                "start_time": now,
                "end_time": wait_until,
                "pending_task_ids": [task.id for _, _, _, task in self.pending_tasks],
                "reason": "No AMRs currently available",
            },
        )

    def _schedule_charge_cycle(self, amr: AMR, now: float) -> bool:
        if getattr(amr, "is_charging", False):
            return True

        current_loc = self.locations[amr.location_name]
        plan = self._plan_return_to_charge(amr, current_loc, now, reserve=True)
        if plan is None:
            self.failed_tasks.append(
                {
                    "task_id": f"CHARGE-{amr.id}",
                    "reason": f"No route to charge location for {amr.id}",
                }
            )
            return False

        charge_duration = amr.charge_duration_sec_to_full()
        charge_start = plan["finish_time"]
        charge_finish = charge_start + charge_duration

        amr.is_charging = True
        amr.available_time = charge_finish
        amr.location_name = plan["end_location"]

        self.push_event(
            now,
            "charge_cycle_start",
            {
                "amr_id": amr.id,
                "travel_segments": plan["segments"],
                "travel_finish": plan["finish_time"],
                "charge_start": charge_start,
                "charge_finish": charge_finish,
                "charge_duration": charge_duration,
            },
        )

        self.push_event(
            charge_finish,
            "charge_cycle_complete",
            {
                "amr_id": amr.id,
                "charge_duration": charge_duration,
            },
        )
        return True

    def _schedule_recharge_for_amr(self, amr: AMR, now: float):
        current_loc = self.locations[amr.location_name]
        charge_plan = self._plan_return_to_charge(
            amr,
            current_loc,
            now,
            reserve=True,
        )

        if charge_plan is None:
            self.failed_tasks.append(
                {
                    "task_id": f"RECHARGE-{amr.id}",
                    "reason": f"Could not route {amr.id} to charge location",
                }
            )
            return

        charge_duration = amr.charge_duration_sec_to_full()
        charge_start = charge_plan["finish_time"]
        charge_finish = charge_start + charge_duration

        amr.available_time = charge_finish
        amr.total_busy_time += charge_plan["travel_sec"] + charge_duration

        self.push_event(
            now,
            "recharge_start",
            {
                "amr_id": amr.id,
                "segments": charge_plan["segments"],
                "start_time": now,
                "arrival_time": charge_plan["finish_time"],
                "charge_start": charge_start,
                "charge_finish": charge_finish,
            },
        )

        self.push_event(
            charge_finish,
            "recharge_complete",
            {
                "amr_id": amr.id,
                "finish_time": charge_finish,
            },
        )

    def _estimate_task_for_amr(self, amr: AMR, task: Task, reserve: bool = False):
        try:
            if task.pickup not in self.locations or task.dropoff not in self.locations:
                return None
            if task.payload not in self.payloads:
                return None

            payload = self.payloads[task.payload]
            if not amr.can_carry(payload):
                return None

            amr_loc = self.locations[amr.location_name]
            pickup_loc = self.locations[task.pickup]
            dropoff_loc = self.locations[task.dropoff]
            route_rules = self._resolve_task_route_rules(task)

            to_pickup_est = (
                self._same_floor_segments(amr, amr_loc, pickup_loc, rules=route_rules)
                if amr_loc.floor == pickup_loc.floor
                else None
            )
            loaded_est = (
                self._same_floor_segments(
                    amr, pickup_loc, dropoff_loc, rules=route_rules
                )
                if pickup_loc.floor == dropoff_loc.floor
                else None
            )
            to_pickup_sec = to_pickup_est[1] if to_pickup_est else 0.0
            loaded_sec = loaded_est[1] if loaded_est else 0.0

            t = max(self.current_time, amr.available_time, task.release_time)
            charge_ready_time, charge_segments, _ = self._plan_charge_cycle_if_needed(
                amr, payload, to_pickup_sec, loaded_sec, t
            )
            t = charge_ready_time

            total = sum(seg["duration"] for seg in charge_segments)
            segments = list(charge_segments)
            current_location = amr_loc

            def move_between(
                location_a: Location, location_b: Location, current_time_value: float
            ) -> Tuple[float, Location, Optional[List[dict]], float]:
                nonlocal total

                if location_a.floor == location_b.floor:
                    route = self._same_floor_segments(
                        amr, location_a, location_b, rules=route_rules
                    )
                    if route is None:
                        return math.inf, location_b, None, 0.0
                    same_segments, route_duration, _ = route
                    total += route_duration
                    return (
                        current_time_value + route_duration,
                        location_b,
                        same_segments,
                        route_duration,
                    )

                plan = self._nearest_compatible_lift_plan(
                    current_time_value,
                    amr,
                    location_a,
                    location_b,
                    payload,
                    rules=route_rules,
                )
                if plan is None:
                    return math.inf, location_b, None, 0.0

                segment_duration = plan["final_finish"] - current_time_value
                total += segment_duration

                if reserve:
                    plan["lift"].available_time = plan["lift_finish"]
                    plan["lift"].current_floor = location_b.floor

                transfer_segments = list(plan["to_lift_segments"])
                transfer_segments.append(
                    {
                        "type": "lift_transfer",
                        "lift_id": plan["lift"].id,
                        "from": plan["origin_lift"].name,
                        "to": plan["destination_lift"].name,
                        "from_floor": location_a.floor,
                        "to_floor": location_b.floor,
                        "wait_time": plan["wait_time"],
                        "duration": plan["lift_finish"] - plan["lift_start"],
                        "distance_m": plan["vertical_distance_m"],
                        "vertical_distance_m": plan["vertical_distance_m"],
                    }
                )
                transfer_segments.extend(plan["from_lift_segments"])
                return (
                    plan["final_finish"],
                    location_b,
                    transfer_segments,
                    segment_duration,
                )

            travel_to_pickup_sec = 0.0
            t, current_location, new_segments, seg_time = move_between(
                current_location, pickup_loc, t
            )
            if new_segments is None or math.isinf(t):
                return None
            travel_to_pickup_sec += seg_time
            segments.extend(new_segments)

            pickup_start = self._find_next_available_time(
                pickup_loc.name,
                t,
                self.load_unload_time_sec,
            )
            pickup_wait = pickup_start - t
            if pickup_wait > 0:
                segments.append(
                    {
                        "type": "wait_for_location",
                        "from": pickup_loc.name,
                        "to": pickup_loc.name,
                        "duration": pickup_wait,
                        "distance_m": 0.0,
                        "location": pickup_loc.name,
                    }
                )
                total += pickup_wait
                t = pickup_start

            if reserve:
                self._reserve_location(
                    pickup_loc.name,
                    t,
                    t + self.load_unload_time_sec,
                )

            t += self.load_unload_time_sec
            total += self.load_unload_time_sec
            segments.append(
                {
                    "type": "pickup",
                    "location": pickup_loc.name,
                    "duration": self.load_unload_time_sec,
                }
            )

            loaded_travel_sec = 0.0
            t, current_location, new_segments, seg_time = move_between(
                current_location, dropoff_loc, t
            )
            if new_segments is None or math.isinf(t):
                return None
            loaded_travel_sec += seg_time
            segments.extend(new_segments)

            dropoff_start = self._find_next_available_time(
                dropoff_loc.name,
                t,
                self.load_unload_time_sec,
            )
            dropoff_wait = dropoff_start - t
            if dropoff_wait > 0:
                segments.append(
                    {
                        "type": "wait_for_location",
                        "from": dropoff_loc.name,
                        "to": dropoff_loc.name,
                        "duration": dropoff_wait,
                        "distance_m": 0.0,
                        "location": dropoff_loc.name,
                    }
                )
                total += dropoff_wait
                t = dropoff_start

            if reserve:
                self._reserve_location(
                    dropoff_loc.name,
                    t,
                    t + self.load_unload_time_sec,
                )

            t += self.load_unload_time_sec
            total += self.load_unload_time_sec
            segments.append(
                {
                    "type": "dropoff",
                    "location": dropoff_loc.name,
                    "duration": self.load_unload_time_sec,
                }
            )

            actual_energy_kwh = total_route_energy_kwh(
                amr, payload, travel_to_pickup_sec, loaded_travel_sec
            )

            projected_battery_soc_after = (
                100.0
                * max(0.0, amr.battery_energy_kwh() - actual_energy_kwh)
                / max(amr.battery_capacity_kwh, 1e-9)
            )

            end_location_name = dropoff_loc.name

            if reserve:
                if charge_segments:
                    amr.total_charge_time += charge_segments[0]["duration"]
                    amr.charge_to_full()

                amr.consume_energy(actual_energy_kwh)
                battery_soc_after = amr.battery_soc_percent
            else:
                battery_soc_after = projected_battery_soc_after

            return {
                "finish_time": t,
                "duration": total,
                "segments": segments,
                "end_location": end_location_name,
                "energy_kwh": actual_energy_kwh,
                "battery_soc_after": battery_soc_after,
            }
        except Exception:
            return None

    def _select_best_assignment(self) -> Optional[Tuple[AMR, Task, dict]]:
        if not self.pending_tasks:
            return None

        best = None
        best_finish = math.inf

        for _, _, _, task in self.pending_tasks:
            for amr in self.amrs:
                if getattr(amr, "is_charging", False):
                    continue

                if self._needs_post_task_recharge(amr):
                    continue

                estimate = self._estimate_task_for_amr(amr, task, reserve=False)
                if estimate is None:
                    continue

                if estimate["finish_time"] < best_finish:
                    best_finish = estimate["finish_time"]
                    best = (amr, task, estimate)

        return best

    def _remove_pending_task(self, target_task: Task):
        rebuilt = []
        removed = False
        while self.pending_tasks:
            item = heapq.heappop(self.pending_tasks)
            if not removed and item[3].id == target_task.id:
                removed = True
                continue
            rebuilt.append(item)
        for item in rebuilt:
            heapq.heappush(self.pending_tasks, item)

    # Task Runner - steps thru sequentially until task end

    def _try_assign_tasks(self, now: float):
        self.current_time = max(self.current_time, now)

        while self.pending_tasks:
            # First, send any idle AMRs that need recharge to charge immediately
            charge_scheduled = False
            for amr in self.amrs:
                if getattr(amr, "is_charging", False):
                    continue
                if amr.available_time > self.current_time:
                    continue
                if self._needs_post_task_recharge(amr):
                    if self._schedule_charge_cycle(amr, self.current_time):
                        charge_scheduled = True

            if charge_scheduled:
                # Re-evaluate after charge events have been queued
                continue

            choice = self._select_best_assignment()
            if choice is None:
                self._create_wait_event_for_pending_tasks(self.current_time)
                return

            amr, task, _ = choice
            committed = self._estimate_task_for_amr(amr, task, reserve=True)

            if committed is None:
                self._remove_pending_task(task)
                self.failed_tasks.append(
                    {
                        "task_id": task.id,
                        "reason": "No feasible AMR/lift/battery/graph combination",
                    }
                )
                continue

            self._remove_pending_task(task)
            start_time = max(self.current_time, amr.available_time, task.release_time)
            previous_location = amr.location_name
            amr.total_busy_time += committed["duration"]
            amr.available_time = committed["finish_time"]
            amr.location_name = committed["end_location"]
            amr.completed_tasks += 1

            self.log_step(
                event_time=start_time,
                event_type="task_assigned",
                task_id=task.id,
                amr_id=amr.id,
                details=f"Assigned task to {amr.id}",
                from_location=task.pickup,
                to_location=task.dropoff,
                payload_name=task.payload,
                task_duration_sec=committed["duration"],
                amr_location_before=previous_location,
                amr_location_after=committed["end_location"],
                status="start",
            )

            segment_start_time = start_time

            for segment in committed["segments"]:
                from_node = segment.get("from", "")
                to_node = segment.get("to", "")

                from_coords = self.graph_nodes.get(from_node)
                to_coords = self.graph_nodes.get(to_node)

                wait_time = segment.get("wait_time", 0.0)
                duration = segment.get("duration", 0.0)

                if wait_time > 0:
                    self.log_step(
                        event_time=segment_start_time,
                        event_type="segment_wait",
                        task_id=task.id,
                        amr_id=amr.id,
                        details=json.dumps(segment, ensure_ascii=False),
                        from_location=from_node or task.pickup,
                        to_location=to_node or task.dropoff,
                        payload_name=task.payload,
                        lift_id=segment.get("lift_id", ""),
                        duration_sec=wait_time,
                        wait_time_sec=wait_time,
                        distance_m=0.0,
                        segment_type="wait",
                        start_time=segment_start_time,
                        end_time=segment_start_time + wait_time,
                        start_node=from_node,
                        end_node=from_node,
                        start_x=getattr(from_coords, "x", None),
                        start_y=getattr(from_coords, "y", None),
                        start_floor=getattr(from_coords, "floor", None),
                        end_x=getattr(from_coords, "x", None),
                        end_y=getattr(from_coords, "y", None),
                        end_floor=getattr(from_coords, "floor", None),
                        status="waiting",
                    )
                    segment_start_time += wait_time

                segment_end_time = segment_start_time + duration

                self.log_step(
                    event_time=segment_start_time,
                    event_type=f"segment_{segment.get('type', '')}",
                    task_id=task.id,
                    amr_id=amr.id,
                    details=json.dumps(
                        {
                            **segment,
                            "from_x": getattr(from_coords, "x", None),
                            "from_y": getattr(from_coords, "y", None),
                            "to_x": getattr(to_coords, "x", None),
                            "to_y": getattr(to_coords, "y", None),
                            "from_floor": getattr(from_coords, "floor", None),
                            "to_floor": getattr(to_coords, "floor", None),
                        },
                        ensure_ascii=False,
                    ),
                    from_location=from_node or task.pickup,
                    to_location=to_node or task.dropoff,
                    payload_name=task.payload,
                    lift_id=segment.get("lift_id", ""),
                    duration_sec=duration,
                    wait_time_sec=wait_time,
                    distance_m=segment.get("distance_m", 0.0),
                    segment_type=segment.get("type", ""),
                    start_time=segment_start_time,
                    end_time=segment_end_time,
                    start_node=from_node,
                    end_node=to_node,
                    start_x=getattr(from_coords, "x", None),
                    start_y=getattr(from_coords, "y", None),
                    start_floor=getattr(from_coords, "floor", None),
                    end_x=getattr(to_coords, "x", None),
                    end_y=getattr(to_coords, "y", None),
                    end_floor=getattr(to_coords, "floor", None),
                    status="completed",
                )

                segment_start_time = segment_end_time

            self.push_event(
                committed["finish_time"],
                "task_complete",
                {
                    "task": task,
                    "amr_id": amr.id,
                    "start_time": start_time,
                    "finish_time": committed["finish_time"],
                    "duration": committed["duration"],
                    "target_time": task.target_time,
                    "segments": committed["segments"],
                    "energy_kwh": committed["energy_kwh"],
                    "battery_soc_after": amr.battery_soc_percent,
                },
            )

    # def _try_assign_tasks(self, now: float):
    #     self.current_time = max(self.current_time, now)
    #     while True:
    #         choice = self._select_best_assignment()
    #         if choice is None:
    #             return
    #         amr, task, _ = choice
    #         committed = self._estimate_task_for_amr(amr, task, reserve=True)
    #         if committed is None:
    #             self._remove_pending_task(task)
    #             self.failed_tasks.append(
    #                 {
    #                     "task_id": task.id,
    #                     "reason": "No feasible AMR/lift/battery/graph combination",
    #                 }
    #             )
    #             continue

    #         self._remove_pending_task(task)
    #         start_time = max(self.current_time, amr.available_time, task.release_time)
    #         previous_location = amr.location_name
    #         amr.total_busy_time += committed["duration"]
    #         amr.available_time = committed["finish_time"]
    #         amr.location_name = committed["end_location"]
    #         amr.completed_tasks += 1

    #         # Log that the task has been assigned

    #         self.log_step(
    #             event_time=start_time,
    #             event_type="task_assigned",
    #             task_id=task.id,
    #             amr_id=amr.id,
    #             details=f"Assigned task to {amr.id}",
    #             from_location=task.pickup,
    #             to_location=task.dropoff,
    #             payload_name=task.payload,
    #             task_duration_sec=committed["duration"],
    #             amr_location_before=previous_location,
    #             amr_location_after=committed["end_location"],
    #             status="start",
    #         )

    #         segment_start_time = start_time

    #         for segment in committed["segments"]:
    #             from_node = segment.get("from", "")
    #             to_node = segment.get("to", "")

    #             from_coords = self.graph_nodes.get(from_node)
    #             to_coords = self.graph_nodes.get(to_node)

    #             wait_time = segment.get("wait_time", 0.0)
    #             duration = segment.get("duration", 0.0)

    #             if wait_time > 0:
    #                 self.log_step(
    #                     event_time=segment_start_time,
    #                     event_type="segment_wait",
    #                     task_id=task.id,
    #                     amr_id=amr.id,
    #                     details=json.dumps(segment, ensure_ascii=False),
    #                     from_location=from_node or task.pickup,
    #                     to_location=to_node or task.dropoff,
    #                     payload_name=task.payload,
    #                     lift_id=segment.get("lift_id", ""),
    #                     duration_sec=wait_time,
    #                     wait_time_sec=wait_time,
    #                     distance_m=0.0,
    #                     segment_type="wait",
    #                     start_time=segment_start_time,
    #                     end_time=segment_start_time + wait_time,
    #                     start_node=from_node,
    #                     end_node=from_node,
    #                     start_x=getattr(from_coords, "x", None),
    #                     start_y=getattr(from_coords, "y", None),
    #                     start_floor=getattr(from_coords, "floor", None),
    #                     end_x=getattr(from_coords, "x", None),
    #                     end_y=getattr(from_coords, "y", None),
    #                     end_floor=getattr(from_coords, "floor", None),
    #                     status="waiting",
    #                 )
    #                 segment_start_time += wait_time

    #             segment_end_time = segment_start_time + duration

    #             self.log_step(
    #                 event_time=segment_start_time,
    #                 event_type=f"segment_{segment.get('type', '')}",
    #                 task_id=task.id,
    #                 amr_id=amr.id,
    #                 details=json.dumps(
    #                     {
    #                         **segment,
    #                         "from_x": getattr(from_coords, "x", None),
    #                         "from_y": getattr(from_coords, "y", None),
    #                         "to_x": getattr(to_coords, "x", None),
    #                         "to_y": getattr(to_coords, "y", None),
    #                         "from_floor": getattr(from_coords, "floor", None),
    #                         "to_floor": getattr(to_coords, "floor", None),
    #                     },
    #                     ensure_ascii=False,
    #                 ),
    #                 from_location=from_node or task.pickup,
    #                 to_location=to_node or task.dropoff,
    #                 payload_name=task.payload,
    #                 lift_id=segment.get("lift_id", ""),
    #                 duration_sec=duration,
    #                 wait_time_sec=wait_time,
    #                 distance_m=segment.get("distance_m", 0.0),
    #                 segment_type=segment.get("type", ""),
    #                 start_time=segment_start_time,
    #                 end_time=segment_end_time,
    #                 start_node=from_node,
    #                 end_node=to_node,
    #                 start_x=getattr(from_coords, "x", None),
    #                 start_y=getattr(from_coords, "y", None),
    #                 start_floor=getattr(from_coords, "floor", None),
    #                 end_x=getattr(to_coords, "x", None),
    #                 end_y=getattr(to_coords, "y", None),
    #                 end_floor=getattr(to_coords, "floor", None),
    #                 status="completed",
    #             )

    #             segment_start_time = segment_end_time

    #         # Task complete

    #         self.push_event(
    #             committed["finish_time"],
    #             "task_complete",
    #             {
    #                 "task": task,
    #                 "amr_id": amr.id,
    #                 "start_time": start_time,
    #                 "finish_time": committed["finish_time"],
    #                 "duration": committed["duration"],
    #                 "segments": committed["segments"],
    #                 "energy_kwh": committed["energy_kwh"],
    #                 "battery_soc_after": amr.battery_soc_percent,
    #             },
    #         )

    #         # Does the AMR need to be recharged?
    #         # Schedule recharge after this task if battery is below reserve
    #         if self._needs_post_task_recharge(amr):
    #             self._schedule_recharge_for_amr(amr, committed["finish_time"])
    #         break

    def run(self):
        while True:
            with self.lock:
                if not self.events:
                    if self.stop_requested:
                        break
                else:
                    event = heapq.heappop(self.events)
                    self.current_time = max(self.current_time, event.time)
                    self._handle_event(event)
                    continue
            if self.stop_requested:
                break
            time.sleep(0.05 / max(self.clock.tick_rate, 1e-9))

    def _handle_event(self, event: Event):
        if event.event_type == "task_release":
            task: Task = event.payload["task"]
            self._queue_pending_task(task)
            self._try_assign_tasks(event.time)
        elif event.event_type == "task_complete":
            task: Task = event.payload["task"]
            self.log_step(
                event_time=event.payload["finish_time"],
                event_type="task_complete",
                task_id=task.id,
                amr_id=event.payload["amr_id"],
                details=f"Task {task.id} completed",
                from_location=task.pickup,
                to_location=task.dropoff,
                payload_name=task.payload,
                duration_sec=0.0,
                wait_time_sec=0.0,
                distance_m=0.0,
                status="finish",
            )

            self.completed_task_records.append(
                {
                    "task_id": task.id,
                    "pickup": task.pickup,
                    "dropoff": task.dropoff,
                    "payload": task.payload,
                    "amr_id": event.payload["amr_id"],
                    "start_datetime": self.clock.format_sim_time(
                        event.payload["start_time"]
                    ),
                    "finish_datetime": self.clock.format_sim_time(
                        event.payload["finish_time"]
                    ),
                    "duration_hms": format_duration(event.payload["duration"]),
                    "target_duration_hms": (
                        format_duration(event.payload["target_time"])
                        if event.payload.get("target_time", 0.0) > 0
                        else ""
                    ),
                    "overrun": (
                        event.payload["duration"]
                        > event.payload.get("target_time", 0.0)
                        if event.payload.get("target_time", 0.0) > 0
                        else False
                    ),
                    "overrun_sec": (
                        round(
                            event.payload["duration"] - event.payload["target_time"], 3
                        )
                        if event.payload.get("target_time", 0.0) > 0
                        and event.payload["duration"] > event.payload["target_time"]
                        else 0.0
                    ),
                    "energy_kwh": round(event.payload["energy_kwh"], 4),
                    "battery_soc_after": round(event.payload["battery_soc_after"], 2),
                    "segments": event.payload["segments"],
                }
            )

            target_time = event.payload.get("target_time", 0.0)
            actual_duration = event.payload["duration"]

            if target_time > 0 and actual_duration > target_time:
                self.push_event(
                    event.time,
                    "task_overrun",
                    {
                        "task": task,
                        "amr_id": event.payload["amr_id"],
                        "actual_duration": actual_duration,
                        "target_time": target_time,
                        "overrun_duration": actual_duration - target_time,
                        "start_time": event.payload["start_time"],
                        "finish_time": event.payload["finish_time"],
                    },
                )
            self._try_assign_tasks(event.time)

        elif event.event_type == "task_wait":
            self.log_step(
                event_time=event.payload["start_time"],
                event_type="task_wait",
                details=event.payload["reason"],
                duration_sec=event.payload["end_time"] - event.payload["start_time"],
                start_time=event.payload["start_time"],
                end_time=event.payload["end_time"],
                status="waiting",
            )
            self._try_assign_tasks(event.time)

        elif event.event_type == "charge_cycle_start":
            amr = next(a for a in self.amrs if a.id == event.payload["amr_id"])
            segment_start_time = event.time

            for segment in event.payload["travel_segments"]:
                from_node = segment.get("from", "")
                to_node = segment.get("to", "")
                from_coords = self.graph_nodes.get(from_node)
                to_coords = self.graph_nodes.get(to_node)
                duration = segment.get("duration", 0.0)
                segment_end_time = segment_start_time + duration

                self.log_step(
                    event_time=segment_start_time,
                    event_type=f"segment_{segment.get('type', '')}",
                    amr_id=amr.id,
                    details=json.dumps(segment, ensure_ascii=False),
                    from_location=from_node,
                    to_location=to_node,
                    duration_sec=duration,
                    distance_m=segment.get("distance_m", 0.0),
                    segment_type=segment.get("type", ""),
                    start_time=segment_start_time,
                    end_time=segment_end_time,
                    start_node=from_node,
                    end_node=to_node,
                    start_x=getattr(from_coords, "x", None),
                    start_y=getattr(from_coords, "y", None),
                    start_floor=getattr(from_coords, "floor", None),
                    end_x=getattr(to_coords, "x", None),
                    end_y=getattr(to_coords, "y", None),
                    end_floor=getattr(to_coords, "floor", None),
                    status="completed",
                )
                segment_start_time = segment_end_time

            self.log_step(
                event_time=event.payload["charge_start"],
                event_type="segment_charge",
                amr_id=amr.id,
                from_location=self.charge_location_name,
                to_location=self.charge_location_name,
                duration_sec=event.payload["charge_duration"],
                segment_type="charge",
                start_time=event.payload["charge_start"],
                end_time=event.payload["charge_finish"],
                start_node=self.charge_location_name,
                end_node=self.charge_location_name,
                status="charging",
            )

        elif event.event_type == "charge_cycle_complete":
            amr = next(a for a in self.amrs if a.id == event.payload["amr_id"])
            amr.total_charge_time += event.payload["charge_duration"]
            amr.charge_to_full()
            amr.is_charging = False

            self.log_step(
                event_time=event.time,
                event_type="charge_cycle_complete",
                amr_id=amr.id,
                details=f"{amr.id} fully charged",
                from_location=self.charge_location_name,
                to_location=self.charge_location_name,
                status="finish",
            )

            self._try_assign_tasks(event.time)

        elif event.event_type == "task_overrun":
            task: Task = event.payload["task"]

            self.log_step(
                event_time=event.payload["finish_time"],
                event_type="task_overrun",
                task_id=task.id,
                amr_id=event.payload["amr_id"],
                details=(
                    f"Task {task.id} exceeded target by "
                    f"{event.payload['overrun_duration']:.3f} seconds"
                ),
                from_location=task.pickup,
                to_location=task.dropoff,
                payload_name=task.payload,
                duration_sec=event.payload["actual_duration"],
                task_duration_sec=event.payload["target_time"],
                status="overrun",
            )

    # def _handle_event(self, event: Event):
    #     if event.event_type == "task_release":
    #         task: Task = event.payload["task"]
    #         self._queue_pending_task(task)
    #         self._try_assign_tasks(event.time)
    #     elif event.event_type == "task_complete":
    #         task: Task = event.payload["task"]
    #         self.log_step(
    #             event_time=event.payload["finish_time"],
    #             event_type="task_complete",
    #             task_id=task.id,
    #             amr_id=event.payload["amr_id"],
    #             details=f"Task {task.id} completed",
    #             from_location=task.pickup,
    #             to_location=task.dropoff,
    #             payload_name=task.payload,
    #             duration_sec=0.0,
    #             wait_time_sec=0.0,
    #             distance_m=0.0,
    #             status="finish",
    #         )

    #         self.completed_task_records.append(
    #             {
    #                 "task_id": task.id,
    #                 "pickup": task.pickup,
    #                 "dropoff": task.dropoff,
    #                 "payload": task.payload,
    #                 "amr_id": event.payload["amr_id"],
    #                 "start_datetime": self.clock.format_sim_time(
    #                     event.payload["start_time"]
    #                 ),
    #                 "finish_datetime": self.clock.format_sim_time(
    #                     event.payload["finish_time"]
    #                 ),
    #                 "duration_hms": format_duration(event.payload["duration"]),
    #                 "energy_kwh": round(event.payload["energy_kwh"], 4),
    #                 "battery_soc_after": round(event.payload["battery_soc_after"], 2),
    #                 "segments": event.payload["segments"],
    #             }
    #         )
    #         self._try_assign_tasks(event.time)
    #     elif event.event_type == "recharge_start":
    #         amr = next(a for a in self.amrs if a.id == event.payload["amr_id"])

    #         segment_start_time = event.payload["start_time"]
    #         for segment in event.payload["segments"]:
    #             from_node = segment.get("from", "")
    #             to_node = segment.get("to", "")

    #             from_coords = self.graph_nodes.get(from_node)
    #             to_coords = self.graph_nodes.get(to_node)

    #             duration = segment.get("duration", 0.0)
    #             segment_end_time = segment_start_time + duration

    #             self.log_step(
    #                 event_time=segment_start_time,
    #                 event_type=f"segment_{segment.get('type', '')}",
    #                 amr_id=amr.id,
    #                 details=json.dumps(segment, ensure_ascii=False),
    #                 from_location=from_node,
    #                 to_location=to_node,
    #                 duration_sec=duration,
    #                 distance_m=segment.get("distance_m", 0.0),
    #                 segment_type=segment.get("type", ""),
    #                 start_time=segment_start_time,
    #                 end_time=segment_end_time,
    #                 start_node=from_node,
    #                 end_node=to_node,
    #                 start_x=getattr(from_coords, "x", None),
    #                 start_y=getattr(from_coords, "y", None),
    #                 start_floor=getattr(from_coords, "floor", None),
    #                 end_x=getattr(to_coords, "x", None),
    #                 end_y=getattr(to_coords, "y", None),
    #                 end_floor=getattr(to_coords, "floor", None),
    #                 status="completed",
    #             )

    #             segment_start_time = segment_end_time

    #         self.log_step(
    #             event_time=event.payload["charge_start"],
    #             event_type="segment_charge",
    #             amr_id=amr.id,
    #             from_location=self.charge_location_name,
    #             to_location=self.charge_location_name,
    #             duration_sec=event.payload["charge_finish"]
    #             - event.payload["charge_start"],
    #             segment_type="charge",
    #             start_time=event.payload["charge_start"],
    #             end_time=event.payload["charge_finish"],
    #             start_node=self.charge_location_name,
    #             end_node=self.charge_location_name,
    #             status="charging",
    #         )

    #     elif event.event_type == "recharge_complete":
    #         amr = next(a for a in self.amrs if a.id == event.payload["amr_id"])
    #         charge_duration = amr.charge_duration_sec_to_full()
    #         amr.total_charge_time += charge_duration
    #         amr.charge_to_full()

    #         self.log_step(
    #             event_time=event.payload["finish_time"],
    #             event_type="recharge_complete",
    #             amr_id=amr.id,
    #             details=f"{amr.id} recharge complete",
    #             from_location=self.charge_location_name,
    #             to_location=self.charge_location_name,
    #             status="finish",
    #         )

    #         self._try_assign_tasks(event.time)

    def request_stop(self):
        with self.lock:
            self.stop_requested = True

    def log_step(
        self,
        event_time: float,
        event_type: str = "",
        task_id: str = "",
        amr_id: str = "",
        details: str = "",
        from_location: str = "",
        to_location: str = "",
        payload_name: str = "",
        lift_id: str = "",
        duration_sec: float = 0.0,
        wait_time_sec: float = 0.0,
        distance_m: float = 0.0,
        task_duration_sec: float = 0.0,
        amr_location_before: str = "",
        amr_location_after: str = "",
        segment_type: str = "",
        start_time: float = 0.0,
        end_time: float = 0.0,
        start_node: str = "",
        end_node: str = "",
        start_x: Optional[float] = None,
        start_y: Optional[float] = None,
        start_floor: Optional[int] = None,
        end_x: Optional[float] = None,
        end_y: Optional[float] = None,
        end_floor: Optional[int] = None,
        status: str = "",
    ):
        if not self.verbose:
            return

        self.verbose_rows.append(
            {
                # Existing schema
                "sim_time_sec": round(event_time, 3),
                "sim_datetime": self.clock.format_sim_time(event_time),
                "event_type": event_type,
                "task_id": task_id,
                "amr_id": amr_id,
                "payload": payload_name,
                "from_location": from_location,
                "to_location": to_location,
                "lift_id": lift_id,
                "duration_sec": round(duration_sec, 3),
                "wait_time_sec": round(wait_time_sec, 3),
                "distance_m": round(distance_m, 3),
                "task_duration_sec": round(task_duration_sec, 3),
                "amr_location_before": amr_location_before,
                "amr_location_after": amr_location_after,
                "details": details,
                # New schema
                "segment_type": segment_type,
                "start_time": self.clock.format_sim_time(start_time),
                "end_time": self.clock.format_sim_time(end_time),
                "start_node": start_node,
                "end_node": end_node,
                "start_x": start_x,
                "start_y": start_y,
                "start_floor": start_floor,
                "end_x": end_x,
                "end_y": end_y,
                "end_floor": end_floor,
                "status": status,
            }
        )

    def write_verbose_csv(self):
        if not self.verbose or not self.verbose_csv_path or not self.verbose_rows:
            return

        fieldnames = [
            "amr_id",
            "task_id",
            "segment_type",
            "start_time",
            "end_time",
            "start_node",
            "end_node",
            "amr_location_before",
            "amr_location_after",
            "start_x",
            "start_y",
            "start_floor",
            "end_x",
            "end_y",
            "end_floor",
            "status",
            "sim_time_sec",
            "sim_datetime",
            "event_type",
            "payload",
            "from_location",
            "to_location",
            "lift_id",
            "duration_sec",
            "wait_time_sec",
            "distance_m",
            "task_duration_sec",
            "details",
        ]

        with open(self.verbose_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.verbose_rows)

    def summary(self) -> dict:
        makespan = 0.0
        if self.completed_task_records:
            finish_times = [
                parse_datetime(x["finish_datetime"])
                for x in self.completed_task_records
            ]
            makespan = max(
                (dt - self.clock.start_datetime).total_seconds() for dt in finish_times
            )
        return {
            "tick_rate": self.clock.tick_rate,
            "sim_datetime": self.clock.format_sim_time(self.current_time),
            "makespan_hms": format_duration(makespan),
            "completed_tasks": len(self.completed_task_records),
            "pending_tasks": len(self.pending_tasks),
            "failed_tasks": self.failed_tasks,
            "amrs": [
                {
                    "amr_id": amr.id,
                    "completed_tasks": amr.completed_tasks,
                    "current_location": amr.location_name,
                    "battery_soc_percent": round(amr.battery_soc_percent, 2),
                    "total_energy_used_kwh": round(amr.total_energy_used_kwh, 4),
                    "total_charge_time_hms": format_duration(amr.total_charge_time),
                }
                for amr in self.amrs
            ],
        }

    def print_summary(self):
        data = self.summary()
        print("\n=== Simulation Summary ===")
        print(json.dumps(data, indent=2))

    def print_completed_tasks(self):
        print("\n=== Completed Tasks ===")
        print(json.dumps(self.completed_task_records, indent=2))


class RuntimeInputThread(threading.Thread):
    def __init__(self, sim: Simulation):
        super().__init__(daemon=True)
        self.sim = sim

    def run(self):
        print("\nInteractive mode enabled.")
        print("Paste a JSON task object to add a task at runtime.")
        print(
            "Use release_time (seconds from simulation start) or release_datetime (ISO format)."
        )
        print("Commands: status, quit")
        while True:
            try:
                line = input().strip()
            except EOFError:
                self.sim.request_stop()
                break

            if not line:
                continue

            if line.lower() == "quit":
                self.sim.request_stop()
                break

            if line.lower() == "status":
                self.sim.print_summary()
                continue

            try:
                task_dict = json.loads(line)
                required = {"id", "pickup", "dropoff", "payload"}
                missing = required - set(task_dict.keys())
                if missing:
                    print(f"Missing task fields: {sorted(missing)}")
                    continue
                task_dict.setdefault("target_time", 0.0)
                task_dict.setdefault("release_time", 0.0)
                task_dict.setdefault("quantity", 1)
                task_dict.setdefault("priority", 100)
                self.sim.add_runtime_task(task_dict)
                print(f"Task {task_dict['id']} added.")
            except Exception as exc:
                print(f"Could not add task: {exc}")


EXAMPLE_CONFIG = {
    "simulation": {"start_datetime": "2026-01-01T08:00:00", "tick_rate": 120.0},
    "building": {
        "load_unload_time_sec": 20.0,
        "floor_height_m": 4.0,
        "charge_location": "Stores",
    },
    "locations": [
        {"name": "Stores", "floor": 0, "x": 0, "y": 0},
        {"name": "Pharmacy", "floor": 0, "x": 20, "y": 8},
        {"name": "Ward-1A", "floor": 1, "x": 10, "y": 2},
        {"name": "Ward-2A", "floor": 2, "x": 12, "y": 5},
        {"name": "Ward-3A", "floor": 3, "x": 16, "y": 4},
        {"name": "Lab", "floor": 2, "x": 3, "y": 15},
    ],
    "corridors": {
        "nodes": [
            {"name": "C0-A", "floor": 0, "x": 4, "y": 0},
            {"name": "C0-B", "floor": 0, "x": 10, "y": 0},
            {"name": "C0-C", "floor": 0, "x": 16, "y": 4},
            {"name": "C1-A", "floor": 1, "x": 5, "y": 2},
            {"name": "C1-B", "floor": 1, "x": 10, "y": 2},
            {"name": "C2-A", "floor": 2, "x": 5, "y": 2},
            {"name": "C2-B", "floor": 2, "x": 12, "y": 5},
            {"name": "C2-C", "floor": 2, "x": 3, "y": 15},
            {"name": "C3-A", "floor": 3, "x": 5, "y": 2},
            {"name": "C3-B", "floor": 3, "x": 16, "y": 4},
        ],
        "edges": [
            {"from": "Stores", "to": "C0-A"},
            {"from": "C0-A", "to": "C0-B"},
            {"from": "C0-B", "to": "C0-C"},
            {"from": "C0-C", "to": "Pharmacy"},
            {"from": "Lift-1-F0", "to": "C0-B"},
            {"from": "Lift-2-F0", "to": "C0-C"},
            {"from": "Lift-1-F1", "to": "C1-A"},
            {"from": "C1-A", "to": "C1-B"},
            {"from": "C1-B", "to": "Ward-1A"},
            {"from": "Lift-1-F2", "to": "C2-A"},
            {"from": "C2-A", "to": "C2-B"},
            {"from": "C2-B", "to": "Ward-2A"},
            {"from": "C2-B", "to": "C2-C"},
            {"from": "C2-C", "to": "Lab"},
            {"from": "Lift-1-F3", "to": "C3-A"},
            {"from": "C3-A", "to": "C3-B"},
            {"from": "C3-B", "to": "Ward-3A"},
        ],
        "auto_connect": False,
    },
    "route_profiles": {
        "dirty": {
            "allowed_lifts": ["Lift-2"],
            "allowed_nodes": [
                "Pharmacy",
                "Ward-2A",
                "C0-C",
                "C2-B",
                "Lift-2-F0",
                "Lift-2-F2",
            ],
            "allowed_edges": [
                ["Pharmacy", "C0-C"],
                ["C0-C", "Pharmacy"],
                ["C0-C", "Lift-2-F0"],
                ["Lift-2-F0", "C0-C"],
                ["Lift-2-F2", "C2-B"],
                ["C2-B", "Lift-2-F2"],
                ["C2-B", "Ward-2A"],
                ["Ward-2A", "C2-B"],
            ],
        }
    },
    "payloads": [
        {"name": "food_trolley", "weight_kg": 120, "size_units": 1.0},
        {"name": "drugs_box", "weight_kg": 15, "size_units": 0.3},
        {"name": "linen_cart", "weight_kg": 80, "size_units": 0.8},
    ],
    "amrs": [
        {
            "id": "AMR-A",
            "quantity": 2,
            "payload_capacity_kg": 150,
            "payload_size_capacity": 1.0,
            "speed_m_per_sec": 1.2,
            "motor_power_w": 900,
            "battery_capacity_kwh": 6.5,
            "battery_charge_rate_kw": 2.2,
            "recharge_threshold_percent": 20.0,
            "battery_soc_percent": 100.0,
            "start_location": "Stores",
        }
    ],
    "lifts": [
        {
            "id": "Lift-1",
            "served_floors": [0, 1, 2, 3],
            "speed_floors_per_sec": 0.5,
            "door_time_sec": 4,
            "boarding_time_sec": 6,
            "capacity_size_units": 1.0,
            "start_floor": 0,
            "floor_locations": {
                "0": {"x": 5, "y": 2},
                "1": {"x": 5, "y": 2},
                "2": {"x": 5, "y": 2},
                "3": {"x": 5, "y": 2},
            },
        },
        {
            "id": "Lift-2",
            "served_floors": [0, 1, 2, 3],
            "speed_floors_per_sec": 0.67,
            "door_time_sec": 4,
            "boarding_time_sec": 5,
            "capacity_size_units": 1.0,
            "start_floor": 0,
            "floor_locations": {
                "0": {"x": 18, "y": 6},
                "1": {"x": 18, "y": 6},
                "2": {"x": 18, "y": 6},
                "3": {"x": 18, "y": 6},
            },
        },
    ],
    "tasks": [
        {
            "id": "T1",
            "pickup": "Stores",
            "dropoff": "Ward-1A",
            "payload": "food_trolley",
            "release_datetime": "2026-01-01T08:00:00",
            "priority": 10,
        },
        {
            "id": "T2",
            "pickup": "Pharmacy",
            "dropoff": "Ward-2A",
            "payload": "drugs_box",
            "release_datetime": "2026-01-01T08:05:00",
            "priority": 20,
        },
        {
            "id": "TEST1",
            "pickup": "Stores",
            "dropoff": "Pharmacy",
            "payload": "drugs_box",
            "release_datetime": "2026-01-01T08:00:00",
            "priority": 1,
        },
        {
            "id": "DIRTY-1",
            "pickup": "Pharmacy",
            "dropoff": "Ward-2A",
            "payload": "drugs_box",
            "labels": ["dirty"],
            "route_profile": "dirty",
            "release_datetime": "2026-01-01T08:10:00",
            "priority": 15,
        },
    ],
}


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_example_config(path: Path):
    path.write_text(json.dumps(EXAMPLE_CONFIG, indent=2), encoding="utf-8")
    print(f"Example config written to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="AMR delivery simulator with graph routing"
    )
    parser.add_argument("--config", type=str, help="Path to config JSON")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--write-example", type=str)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--verbose-csv", type=str, default="simulation_steps.csv")
    args = parser.parse_args()

    if args.write_example:
        write_example_config(Path(args.write_example))
        return

    if not args.config:
        raise SystemExit(
            "Please provide --config path, or use --write-example example.json first."
        )

    sim = Simulation(
        load_json(args.config), verbose=args.verbose, verbose_csv_path=args.verbose_csv
    )

    input_thread = None
    if args.interactive:
        input_thread = RuntimeInputThread(sim)
        input_thread.start()

    try:
        sim.run()
    except KeyboardInterrupt:
        sim.request_stop()

    print(json.dumps(sim.summary(), indent=2))
    sim.write_verbose_csv()
    if args.verbose:
        print(f"Verbose CSV written to {args.verbose_csv}")


if __name__ == "__main__":
    main()
