import argparse
import csv
import heapq
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================
# AMR Delivery Route Simulator
# ------------------------------------------------------------
# Features
# - Multi-floor building with named locations
# - Lift resources with capacity, speed, and door/boarding timings
# - AMRs with payload, speed, and quantity configurable from JSON
# - Task list can be loaded initially and added at runtime
# - Uses datetimes for release/start/finish timestamps
# - Supports accelerated simulation time via a tick rate
# - Discrete-event simulation for estimated completion times
#
# Run examples:
#   python amr_delivery_simulator.py --config config.json
#   python amr_delivery_simulator.py --config config.json --interactive
#
# While running with --interactive, paste JSON task objects such as:
#   {"id":"T9","pickup":"Stores","dropoff":"Ward-3A","payload":"food_trolley","release_time":120}
#
# Type:
#   status
#   quit
# ============================================================


@dataclass(order=True)
class Event:
    time: float
    priority: int
    event_type: str = field(compare=False)
    payload: dict = field(compare=False, default_factory=dict)


@dataclass
class Location:
    name: str
    floor: int
    x: float
    y: float


@dataclass
class PayloadType:
    name: str
    weight_kg: float
    size_units: float = 1.0


@dataclass
class Task:
    id: str
    pickup: str
    dropoff: str
    payload: str
    release_time: float = 0.0
    quantity: int = 1
    priority: int = 100
    created_during_runtime: bool = False


class SimulationClock:
    def __init__(self, start_datetime: datetime, tick_rate: float = 60.0):
        self.start_datetime = start_datetime
        self.tick_rate = tick_rate

    def sim_seconds_to_datetime(self, seconds: float) -> datetime:
        return self.start_datetime + timedelta(seconds=seconds)

    def format_sim_time(self, seconds: float) -> str:
        return self.sim_seconds_to_datetime(seconds).isoformat(
            sep=" ", timespec="seconds"
        )


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours:02}:{minutes:02}:{secs:02}"
    return f"{hours:02}:{minutes:02}:{secs:02}"


def parse_release_time(task_dict: dict, start_datetime: datetime) -> float:
    if "release_datetime" in task_dict:
        dt = parse_datetime(task_dict["release_datetime"])
        return max(0.0, (dt - start_datetime).total_seconds())
    return float(task_dict.get("release_time", 0.0))


@dataclass
class Lift:
    id: str
    served_floors: List[int]
    speed_floors_per_sec: float
    door_time_sec: float
    boarding_time_sec: float
    capacity_size_units: float = 1.0
    current_floor: int = 0
    available_time: float = 0.0

    def can_serve(self, floor_a: int, floor_b: int) -> bool:
        return floor_a in self.served_floors and floor_b in self.served_floors

    def estimate_trip(
        self, ready_time: float, from_floor: int, to_floor: int, load_size: float
    ) -> Tuple[float, float]:
        if not self.can_serve(from_floor, to_floor):
            return math.inf, math.inf
        if load_size > self.capacity_size_units:
            return math.inf, math.inf

        start_time = max(ready_time, self.available_time)
        reposition = abs(self.current_floor - from_floor) / max(
            self.speed_floors_per_sec, 1e-9
        )
        loaded_travel = abs(to_floor - from_floor) / max(
            self.speed_floors_per_sec, 1e-9
        )
        duration = (
            reposition
            + self.door_time_sec
            + self.boarding_time_sec
            + loaded_travel
            + self.door_time_sec
            + self.boarding_time_sec
        )
        finish_time = start_time + duration
        return start_time, finish_time

    def reserve_trip(
        self, ready_time: float, from_floor: int, to_floor: int, load_size: float
    ) -> Tuple[float, float]:
        start_time, finish_time = self.estimate_trip(
            ready_time, from_floor, to_floor, load_size
        )
        if math.isinf(finish_time):
            raise ValueError(
                f"Lift {self.id} cannot serve trip {from_floor}->{to_floor} for load size {load_size}."
            )
        self.available_time = finish_time
        self.current_floor = to_floor
        return start_time, finish_time


@dataclass
class AMR:
    id: str
    payload_capacity_kg: float
    payload_size_capacity: float
    speed_m_per_sec: float
    available_time: float = 0.0
    location_name: str = ""
    completed_tasks: int = 0
    total_busy_time: float = 0.0

    def can_carry(self, payload: PayloadType) -> bool:
        return (
            payload.weight_kg <= self.payload_capacity_kg
            and payload.size_units <= self.payload_size_capacity
        )


class Simulation:
    def __init__(
        self,
        config: dict,
        verbose: bool = False,
        verbose_csv_path: Optional[str] = None,
    ):
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

        self.floor_height_m = float(config["building"].get("floor_height_m", 4.0))
        self.load_unload_time_sec = float(
            config["building"].get("load_unload_time_sec", 20.0)
        )

        self.locations: Dict[str, Location] = {
            loc["name"]: Location(
                name=loc["name"],
                floor=int(loc["floor"]),
                x=float(loc.get("x", 0.0)),
                y=float(loc.get("y", 0.0)),
            )
            for loc in config["locations"]
        }

        self.payloads: Dict[str, PayloadType] = {
            p["name"]: PayloadType(
                name=p["name"],
                weight_kg=float(p["weight_kg"]),
                size_units=float(p.get("size_units", 1.0)),
            )
            for p in config["payloads"]
        }

        self.lifts: List[Lift] = [
            Lift(
                id=item["id"],
                served_floors=list(item["served_floors"]),
                speed_floors_per_sec=float(item["speed_floors_per_sec"]),
                door_time_sec=float(item.get("door_time_sec", 4.0)),
                boarding_time_sec=float(item.get("boarding_time_sec", 5.0)),
                capacity_size_units=float(item.get("capacity_size_units", 1.0)),
                current_floor=int(item.get("start_floor", 0)),
            )
            for item in config["lifts"]
        ]

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
                        location_name=amr_type.get(
                            "start_location", config["locations"][0]["name"]
                        ),
                    )
                )

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

    # ------------------------- Core Utilities -------------------------

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
        self.log_step(
            event_time=time_value,
            event_type="event_scheduled",
            task_id=(
                (payload or {}).get("task").id if (payload or {}).get("task") else ""
            ),
            amr_id=(payload or {}).get("amr_id", ""),
            details=f"Scheduled event '{event_type}'",
        )

    def schedule_task_release(self, task: Task):
        self.push_event(task.release_time, "task_release", {"task": task})
        self.log_step(
            event_time=task.release_time,
            event_type="task_release_planned",
            task_id=task.id,
            details=f"Task {task.id} will release at {self.clock.format_sim_time(task.release_time)}",
            from_location=task.pickup,
            to_location=task.dropoff,
            payload_name=task.payload,
        )

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
        self.log_step(
            event_time=max(self.current_time, task.release_time),
            event_type="task_queued",
            task_id=task.id,
            details=f"Task queued with priority {task.priority}",
            from_location=task.pickup,
            to_location=task.dropoff,
            payload_name=task.payload,
        )

    def _distance_same_floor(self, a: Location, b: Location) -> float:
        return math.hypot(b.x - a.x, b.y - a.y)

    def _travel_same_floor(self, amr: AMR, start: Location, end: Location) -> float:
        return self._distance_same_floor(start, end) / max(amr.speed_m_per_sec, 1e-9)

    def _nearest_compatible_lift_plan(
        self,
        ready_time: float,
        from_floor: int,
        to_floor: int,
        payload: PayloadType,
    ) -> Tuple[Optional[Lift], float, float]:
        best_lift = None
        best_start = math.inf
        best_finish = math.inf
        for lift in self.lifts:
            start_time, finish_time = lift.estimate_trip(
                ready_time,
                from_floor,
                to_floor,
                payload.size_units,
            )
            if finish_time < best_finish:
                best_lift = lift
                best_start = start_time
                best_finish = finish_time
        return best_lift, best_start, best_finish

    def _estimate_task_for_amr(self, amr: AMR, task: Task, reserve: bool = False):
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

        t = max(self.current_time, amr.available_time, task.release_time)
        total = 0.0
        segments = []
        current_location = amr_loc

        def move_between(
            location_a: Location, location_b: Location, current_time_value: float
        ) -> Tuple[float, Location, Optional[dict]]:
            nonlocal total
            if location_a.floor == location_b.floor:
                walk = self._travel_same_floor(amr, location_a, location_b)
                total += walk
                return (
                    current_time_value + walk,
                    location_b,
                    {
                        "type": "corridor",
                        "from": location_a.name,
                        "to": location_b.name,
                        "duration": walk,
                        "distance_m": self._distance_same_floor(location_a, location_b),
                    },
                )

            start_floor = location_a.floor
            end_floor = location_b.floor
            lift, lift_start, lift_finish = self._nearest_compatible_lift_plan(
                current_time_value,
                start_floor,
                end_floor,
                payload,
            )
            if lift is None:
                return math.inf, location_b, None

            wait = max(0.0, lift_start - current_time_value)
            total += wait + (lift_finish - lift_start)

            if reserve:
                lift.reserve_trip(
                    current_time_value, start_floor, end_floor, payload.size_units
                )

            return (
                lift_finish,
                location_b,
                {
                    "type": "lift",
                    "lift_id": lift.id,
                    "from_floor": start_floor,
                    "to_floor": end_floor,
                    "wait_time": wait,
                    "duration": lift_finish - lift_start,
                },
            )

        t, current_location, segment = move_between(current_location, pickup_loc, t)
        if segment is None or math.isinf(t):
            return None
        segments.append(segment)

        t += self.load_unload_time_sec
        total += self.load_unload_time_sec
        segments.append(
            {
                "type": "pickup",
                "location": pickup_loc.name,
                "duration": self.load_unload_time_sec,
            }
        )

        t, current_location, segment = move_between(current_location, dropoff_loc, t)
        if segment is None or math.isinf(t):
            return None
        segments.append(segment)

        t += self.load_unload_time_sec
        total += self.load_unload_time_sec
        segments.append(
            {
                "type": "dropoff",
                "location": dropoff_loc.name,
                "duration": self.load_unload_time_sec,
            }
        )

        return {
            "finish_time": t,
            "duration": total,
            "segments": segments,
            "end_location": dropoff_loc.name,
        }

    def _select_best_assignment(self) -> Optional[Tuple[AMR, Task, dict]]:
        if not self.pending_tasks:
            return None

        available_tasks = [item[3] for item in self.pending_tasks]
        best: Optional[Tuple[AMR, Task, dict]] = None
        best_finish = math.inf

        for task in available_tasks:
            for amr in self.amrs:
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

    def _try_assign_tasks(self, now: float):
        self.current_time = max(self.current_time, now)

        while True:
            choice = self._select_best_assignment()
            if choice is None:
                return

            amr, task, dry_run = choice

            committed = self._estimate_task_for_amr(amr, task, reserve=True)
            if committed is None:
                self._remove_pending_task(task)
                self.failed_tasks.append(
                    {
                        "task_id": task.id,
                        "reason": "No feasible AMR/lift combination",
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
                amr_location_before=previous_location,
                amr_location_after=committed["end_location"],
                task_duration_sec=committed["duration"],
            )

            for segment in committed["segments"]:
                self.log_step(
                    event_time=start_time,
                    event_type=f"segment_{segment['type']}",
                    task_id=task.id,
                    amr_id=amr.id,
                    details=json.dumps(segment, ensure_ascii=False),
                    from_location=segment.get("from", task.pickup),
                    to_location=segment.get("to", task.dropoff),
                    payload_name=task.payload,
                    lift_id=segment.get("lift_id", ""),
                    duration_sec=segment.get("duration", 0.0),
                    wait_time_sec=segment.get("wait_time", 0.0),
                    distance_m=segment.get("distance_m", 0.0),
                )

            self.push_event(
                committed["finish_time"],
                "task_complete",
                {
                    "task": task,
                    "amr_id": amr.id,
                    "start_time": start_time,
                    "finish_time": committed["finish_time"],
                    "duration": committed["duration"],
                    "segments": committed["segments"],
                },
            )

    # ------------------------- Simulation Loop ------------------------

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
        self.log_step(
            event_time=event.time,
            event_type=f"event_processed_{event.event_type}",
            task_id=event.payload.get("task").id if event.payload.get("task") else "",
            amr_id=event.payload.get("amr_id", ""),
            details=f"Processing event '{event.event_type}'",
        )

        if event.event_type == "task_release":
            task: Task = event.payload["task"]
            self._queue_pending_task(task)
            self._try_assign_tasks(event.time)

        elif event.event_type == "task_complete":
            task: Task = event.payload["task"]
            record = {
                "task_id": task.id,
                "pickup": task.pickup,
                "dropoff": task.dropoff,
                "payload": task.payload,
                "amr_id": event.payload["amr_id"],
                "start_time_sec": round(event.payload["start_time"], 3),
                "finish_time_sec": round(event.payload["finish_time"], 3),
                "duration_sec": round(event.payload["duration"], 3),
                "start_datetime": self.clock.format_sim_time(
                    event.payload["start_time"]
                ),
                "finish_datetime": self.clock.format_sim_time(
                    event.payload["finish_time"]
                ),
                "duration_hms": format_duration(event.payload["duration"]),
                "segments": event.payload["segments"],
                "runtime_added": task.created_during_runtime,
            }
            self.completed_task_records.append(record)
            self.log_step(
                event_time=event.time,
                event_type="task_completed",
                task_id=task.id,
                amr_id=event.payload["amr_id"],
                details=f"Task completed in {format_duration(event.payload['duration'])}",
                from_location=task.pickup,
                to_location=task.dropoff,
                payload_name=task.payload,
                task_duration_sec=event.payload["duration"],
            )
            self._try_assign_tasks(event.time)

    def request_stop(self):
        with self.lock:
            self.stop_requested = True

    def log_step(
        self,
        event_time: float,
        event_type: str,
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
    ):
        if not self.verbose:
            return
        self.verbose_rows.append(
            {
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
            }
        )

    def write_verbose_csv(self):
        if not self.verbose or not self.verbose_csv_path:
            return
        if not self.verbose_rows:
            return
        fieldnames = [
            "sim_time_sec",
            "sim_datetime",
            "event_type",
            "task_id",
            "amr_id",
            "payload",
            "from_location",
            "to_location",
            "lift_id",
            "duration_sec",
            "wait_time_sec",
            "distance_m",
            "task_duration_sec",
            "amr_location_before",
            "amr_location_after",
            "details",
        ]
        with open(self.verbose_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.verbose_rows)

    # --------------------------- Reporting ----------------------------

    def summary(self) -> dict:
        with self.lock:
            makespan = 0.0
            if self.completed_task_records:
                makespan = max(
                    x["finish_time_sec"] for x in self.completed_task_records
                )

            amr_summary = []
            for amr in self.amrs:
                utilisation = 0.0 if makespan <= 0 else amr.total_busy_time / makespan
                amr_summary.append(
                    {
                        "amr_id": amr.id,
                        "completed_tasks": amr.completed_tasks,
                        "available_time_sec": round(amr.available_time, 3),
                        "current_location": amr.location_name,
                        "busy_time_sec": round(amr.total_busy_time, 3),
                        "utilisation": round(utilisation, 4),
                    }
                )

            return {
                "tick_rate": self.clock.tick_rate,
                "sim_time_sec": round(self.current_time, 3),
                "sim_datetime": self.clock.format_sim_time(self.current_time),
                "start_datetime": self.clock.start_datetime.isoformat(
                    sep=" ", timespec="seconds"
                ),
                "makespan_sec": round(makespan, 3),
                "makespan_hms": format_duration(makespan),
                "completion_datetime": self.clock.format_sim_time(makespan),
                "completed_tasks": len(self.completed_task_records),
                "pending_tasks": len(self.pending_tasks),
                "future_events": len(self.events),
                "failed_tasks": self.failed_tasks,
                "amrs": amr_summary,
            }

    def print_summary(self):
        data = self.summary()
        print("\n=== Simulation Summary ===")
        print(json.dumps(data, indent=2))

    def print_completed_tasks(self):
        print("\n=== Completed Tasks ===")
        print(json.dumps(self.completed_task_records, indent=2))


# ---------------------------- CLI Helpers ----------------------------


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
                task_dict.setdefault("release_time", 0.0)
                task_dict.setdefault("quantity", 1)
                task_dict.setdefault("priority", 100)
                self.sim.add_runtime_task(task_dict)
                print(f"Task {task_dict['id']} added.")
            except Exception as exc:
                print(f"Could not add task: {exc}")


# -------------------------- Example Config ---------------------------

EXAMPLE_CONFIG = {
    "simulation": {"start_datetime": "2026-01-01T08:00:00", "tick_rate": 120.0},
    "building": {"floor_height_m": 4.0, "load_unload_time_sec": 20.0},
    "locations": [
        {"name": "Stores", "floor": 0, "x": 0, "y": 0},
        {"name": "Pharmacy", "floor": 0, "x": 20, "y": 8},
        {"name": "Ward-1A", "floor": 1, "x": 10, "y": 2},
        {"name": "Ward-2A", "floor": 2, "x": 12, "y": 5},
        {"name": "Ward-3A", "floor": 3, "x": 16, "y": 4},
        {"name": "Lab", "floor": 2, "x": 3, "y": 15},
    ],
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
            "start_location": "Stores",
        },
        {
            "id": "AMR-B",
            "quantity": 1,
            "payload_capacity_kg": 40,
            "payload_size_capacity": 0.5,
            "speed_m_per_sec": 1.5,
            "start_location": "Pharmacy",
        },
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
        },
        {
            "id": "Lift-2",
            "served_floors": [0, 1, 2, 3],
            "speed_floors_per_sec": 0.67,
            "door_time_sec": 4,
            "boarding_time_sec": 5,
            "capacity_size_units": 1.0,
            "start_floor": 0,
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
            "pickup": "Stores",
            "dropoff": "Ward-2A",
            "payload": "food_trolley",
            "release_datetime": "2026-01-01T08:00:00",
            "priority": 10,
        },
        {
            "id": "T3",
            "pickup": "Pharmacy",
            "dropoff": "Ward-3A",
            "payload": "drugs_box",
            "release_datetime": "2026-01-01T08:01:00",
            "priority": 20,
        },
        {
            "id": "T4",
            "pickup": "Stores",
            "dropoff": "Lab",
            "payload": "linen_cart",
            "release_datetime": "2026-01-01T08:02:00",
            "priority": 30,
        },
    ],
}


def write_example_config(path: Path):
    path.write_text(json.dumps(EXAMPLE_CONFIG, indent=2), encoding="utf-8")
    print(f"Example config written to {path}")


# ------------------------------- Main -------------------------------


def main():
    parser = argparse.ArgumentParser(description="AMR multi-floor delivery simulator")
    parser.add_argument("--config", type=str, help="Path to config JSON")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Allow runtime task insertion from stdin",
    )
    parser.add_argument(
        "--write-example", type=str, help="Write an example JSON config and exit"
    )
    parser.add_argument(
        "--print-tasks",
        action="store_true",
        help="Print completed task details at the end",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Record verbose simulation steps"
    )
    parser.add_argument(
        "--verbose-csv",
        type=str,
        default="simulation_steps.csv",
        help="CSV file path for verbose output",
    )
    args = parser.parse_args()

    if args.write_example:
        write_example_config(Path(args.write_example))
        return

    if not args.config:
        raise SystemExit(
            "Please provide --config path, or use --write-example example.json first."
        )

    config = load_json(args.config)
    sim = Simulation(config, verbose=args.verbose, verbose_csv_path=args.verbose_csv)

    input_thread = None
    if args.interactive:
        input_thread = RuntimeInputThread(sim)
        input_thread.start()

    try:
        sim.run()
    except KeyboardInterrupt:
        sim.request_stop()

    sim.print_summary()
    if args.print_tasks:
        sim.print_completed_tasks()
    sim.write_verbose_csv()
    if args.verbose:
        print(f"Verbose CSV written to {args.verbose_csv}")


if __name__ == "__main__":
    main()
