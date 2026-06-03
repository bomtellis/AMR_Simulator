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

from amr_sim_energy import (
    requires_recharge_before_route,
    total_lift_energy_kwh,
    total_route_energy_kwh,
)
from amr_sim_models import AMR, Event, Lift, Location, PayloadType, Task
from amr_sim_payload_instances import (
    EMPTY_PAYLOAD_NAME,
    PayloadInstanceStore,
    is_empty_payload_name,
    normalise_payload_name,
)
from amr_sim_task_generation import TaskGenerationManager
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
        self.wall_start_time = None
        self.last_progress_update = 0.0
        self.progress_update_interval = 0.2  # seconds
        self.estimated_total_sim_time = 1.0

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
        self.failed_task_ids = set()
        self.location_reservations: Dict[str, List[Tuple[float, float]]] = defaultdict(
            list
        )

        self.payload_instance_store = PayloadInstanceStore()

        # Congestion setup
        building_cfg = config.get("building", {})

        self.edge_reservations: Dict[
            Tuple[str, str], List[Tuple[float, float, str]]
        ] = defaultdict(list)

        self.node_reservations: Dict[str, List[Tuple[float, float, str]]] = defaultdict(
            list
        )
        self.node_clearance_time_sec = float(
            building_cfg.get("node_clearance_time_sec", 0.5)
        )

        self.route_cache: Dict[Tuple[int, str, str, Tuple, Tuple], Optional[dict]] = {}

        self.amr_spacing_m = float(building_cfg.get("amr_spacing_m", 1.5))
        self.edge_max_concurrency = int(building_cfg.get("edge_max_concurrency", 1))
        self.edge_congestion_window_sec = float(
            building_cfg.get("edge_congestion_window_sec", 30.0)
        )
        self.edge_slowdown_per_amr = float(
            building_cfg.get("edge_slowdown_per_amr", 0.15)
        )
        self.min_congestion_speed_factor = float(
            building_cfg.get("min_congestion_speed_factor", 0.45)
        )

        self.load_unload_time_sec = float(
            config["building"].get("load_unload_time_sec", 20.0)
        )
        self.floor_height_m = float(config["building"].get("floor_height_m", 4.0))
        configured_charge_locations = config["building"].get("charge_locations")
        if isinstance(configured_charge_locations, list):
            self.charge_location_names = [
                str(x).strip() for x in configured_charge_locations if str(x).strip()
            ]
        else:
            legacy_charge_location = str(
                config["building"].get("charge_location", "")
            ).strip()
            self.charge_location_names = (
                [legacy_charge_location] if legacy_charge_location else []
            )
        if not self.charge_location_names:
            self.charge_location_names = [config["locations"][0]["name"]]
        # Backwards-compatible current charger label used by existing logging paths.
        self.charge_location_name = self.charge_location_names[0]

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

        # Inventory spaces are finite storage slots inside locations.
        # A drop-off only needs a free compatible slot when the location explicitly
        # defines at least one valid inventory space. Locations with no
        # inventory_spaces, an empty inventory_spaces list, or no valid spaces keep
        # the previous unlimited-storage behaviour.
        self.inventory_spaces_by_location: Dict[str, List[dict]] = {}
        self._init_inventory_spaces(config.get("locations", []))

        # Parse payloads from configuration

        self.payloads: Dict[str, PayloadType] = {}
        for p in config["payloads"]:
            legacy_size = float(p.get("size_units", 1.0))
            raw_items = p.get("items", {}) or {}
            if isinstance(raw_items, list):
                converted_items = {}
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    item_name = str(item.get("name", "")).strip()
                    if item_name:
                        converted_items[item_name] = dict(item)
                raw_items = converted_items
            if not isinstance(raw_items, dict):
                raw_items = {}
            clean_items = {}
            for item_name, item_cfg in raw_items.items():
                item_name = str(item_name).strip()
                if not item_name:
                    continue
                item_cfg = item_cfg if isinstance(item_cfg, dict) else {}
                clean_items[item_name] = {
                    "max": float(item_cfg.get("max", 100)),
                    "top_up_threshold": float(item_cfg.get("top_up_threshold", 15)),
                    "usage_rate": str(item_cfg.get("usage_rate", "scheduled_sporadic")),
                    "consumption_per_day": float(
                        item_cfg.get("consumption_per_day", 0.0)
                    ),
                    "exchange_payload": str(
                        item_cfg.get("exchange_payload", "")
                    ).strip(),
                    "source_location": str(item_cfg.get("source_location", "")).strip(),
                }
            payload_type = PayloadType(
                name=p["name"],
                weight_kg=float(p["weight_kg"]),
                length_m=float(p.get("length_m", legacy_size)),
                width_m=float(p.get("width_m", legacy_size)),
                height_m=float(p.get("height_m", legacy_size)),
                size_units=legacy_size,
                track_items=bool(p.get("track_items", False)),
                items=clean_items,
            )
            # Optional payload-level preference from the visualiser payload dialog.
            # Kept as a runtime attribute so older amr_sim_models.PayloadType
            # dataclasses do not need to change just to carry this scheduling hint.
            payload_type.prefer_multi_stop_amr = bool(
                p.get("prefer_multi_stop_amr", False)
            )
            self.payloads[p["name"]] = payload_type

        # Internal zero-load payload used for empty idle return, recharge and no-load moves.
        # It is deliberately not written as a real payload in verbose output.
        if EMPTY_PAYLOAD_NAME not in self.payloads:
            empty_payload = PayloadType(
                name=EMPTY_PAYLOAD_NAME,
                weight_kg=0.0,
                length_m=0.0,
                width_m=0.0,
                height_m=0.0,
                size_units=0.0,
            )
            empty_payload.prefer_multi_stop_amr = False
            self.payloads[EMPTY_PAYLOAD_NAME] = empty_payload

        # Parse waste streams and departments
        self.waste_streams: Dict[str, dict] = {
            str(item.get("name", "")).strip(): dict(item)
            for item in config.get("waste_streams", [])
            if str(item.get("name", "")).strip()
        }

        self.departments: List[dict] = list(config.get("departments", []))
        self.department_runtime: Dict[str, Dict[str, dict]] = {}
        self.department_task_counter = 0

        self.route_profiles = config.get("route_profiles", {})
        self.task_generation_manager = TaskGenerationManager(
            config=config,
            clock=self.clock,
            locations=self.locations,
            payloads=self.payloads,
        )
        self.task_generation_interval_sec = float(
            (config.get("task_generation", {}) or {}).get("update_interval_sec", 900.0)
        )
        self.task_generation_horizon_sec = self._task_generation_horizon_seconds(config)

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
                capacity_length_m=float(item.get("capacity_length_m", 2.8)),
                capacity_width_m=float(item.get("capacity_width_m", 1.8)),
                capacity_height_m=float(item.get("capacity_height_m", 2.1)),
                capacity_size_units=float(item.get("capacity_size_units", 1.0)),
                current_floor=int(item.get("start_floor", 0)),
                car_mass_kg=float(item.get("car_mass_kg", 1200.0)),
                counterweight_ratio=float(item.get("counterweight_ratio", 0.5)),
                travel_efficiency=float(item.get("travel_efficiency", 0.75)),
                door_power_w=float(item.get("door_power_w", 800.0)),
                standby_power_w=float(item.get("standby_power_w", 120.0)),
                regen_efficiency=float(item.get("regen_efficiency", 0.2)),
                health_percent=float(item.get("health_percent", 100.0)),
                health_loss_per_journey_percent=float(
                    item.get("health_loss_per_journey_percent", 0.05)
                ),
                mean_time_between_failures_hours=float(
                    item.get("mean_time_between_failures_hours", 720.0)
                ),
                mean_time_to_repair_hours=float(
                    item.get("mean_time_to_repair_hours", 4.0)
                ),
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
                payload_slots = self._normalise_configured_payload_slots(amr_type)
                primary_slot = payload_slots[0]
                amr = AMR(
                    id=f"{amr_type['id']}-{i + 1}",
                    payload_capacity_kg=float(primary_slot["payload_capacity_kg"]),
                    payload_length_capacity_m=float(
                        primary_slot["payload_length_capacity_m"]
                    ),
                    payload_width_capacity_m=float(
                        primary_slot["payload_width_capacity_m"]
                    ),
                    payload_height_capacity_m=float(
                        primary_slot["payload_height_capacity_m"]
                    ),
                    length_m=float(amr_type.get("length_m", 0.8)),
                    width_m=float(amr_type.get("width_m", 0.6)),
                    height_m=float(amr_type.get("height_m", 1.2)),
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
                amr.payload_slots = payload_slots
                amr.multi_stop_enabled = bool(
                    amr_type.get("multi_stop_enabled", len(payload_slots) > 1)
                    and len(payload_slots) > 1
                )
                amr.manual_task_compatible = len(payload_slots) == 1
                self.amrs.append(amr)

        # Parse tasks from configuration

        initial_tasks = []
        for task_dict in config.get("tasks", []):
            task_data = dict(task_dict)
            task_data["release_time"] = parse_release_time(
                task_data, self.clock.start_datetime
            )
            task_data.pop("release_datetime", None)
            task = Task(**task_data)
            self._prepare_task_payload_instance(task)
            initial_tasks.append(task)

        for task in initial_tasks:
            self.schedule_task_release(task)

        # Runtime task generation is now handled by amr_sim_task_generation.py.
        # Keep the old department runtime methods below for compatibility only.

        self.estimated_total_sim_time = self._estimate_total_sim_time()

        self.amr_centre_name = config["building"].get("amr_centre", "AMR_CENTRE")
        self.idle_return_window_sec = float(
            config["building"].get("idle_return_window_sec", 300.0)
        )
        self.enable_idle_return = bool(
            config["building"].get("enable_idle_return", True)
        )
        self.synthetic_task_counter = 0

        if getattr(self.task_generation_manager, "generators", []):
            self.push_event(0.0, "generator_tick", {})

    def _task_generation_horizon_seconds(self, config: dict) -> float:
        sim_cfg = config.get("simulation", {}) or {}
        if sim_cfg.get("end_datetime"):
            try:
                return max(
                    0.0,
                    (
                        parse_datetime(sim_cfg["end_datetime"])
                        - self.clock.start_datetime
                    ).total_seconds(),
                )
            except Exception:
                pass
        if sim_cfg.get("duration_hours") is not None:
            return max(0.0, float(sim_cfg.get("duration_hours", 0.0)) * 3600.0)
        if sim_cfg.get("duration_days") is not None:
            return max(0.0, float(sim_cfg.get("duration_days", 0.0)) * 86400.0)

        latest = 0.0
        for task in config.get("tasks", []):
            try:
                latest = max(
                    latest, parse_release_time(dict(task), self.clock.start_datetime)
                )
            except Exception:
                continue
        return max(latest + 86400.0, 86400.0)

    def _normalise_configured_payload_slots(self, amr_type: dict) -> List[dict]:
        raw_slots = (
            amr_type.get("payload_slots", []) if isinstance(amr_type, dict) else []
        )
        slots = []
        if isinstance(raw_slots, list):
            for index, slot in enumerate(raw_slots, start=1):
                if not isinstance(slot, dict):
                    continue
                slots.append(
                    {
                        "name": str(slot.get("name", "")).strip() or f"Slot {index}",
                        "payload_capacity_kg": float(
                            slot.get("payload_capacity_kg", 0.0) or 0.0
                        ),
                        "payload_length_capacity_m": float(
                            slot.get("payload_length_capacity_m", 0.0) or 0.0
                        ),
                        "payload_width_capacity_m": float(
                            slot.get("payload_width_capacity_m", 0.0) or 0.0
                        ),
                        "payload_height_capacity_m": float(
                            slot.get("payload_height_capacity_m", 0.0) or 0.0
                        ),
                    }
                )
        if not slots:
            slots.append(
                {
                    "name": "Slot 1",
                    "payload_capacity_kg": float(
                        amr_type.get("payload_capacity_kg", 100.0) or 100.0
                    ),
                    "payload_length_capacity_m": float(
                        amr_type.get(
                            "payload_length_capacity_m",
                            amr_type.get("payload_size_capacity", 1.0),
                        )
                        or 1.0
                    ),
                    "payload_width_capacity_m": float(
                        amr_type.get(
                            "payload_width_capacity_m",
                            amr_type.get("payload_size_capacity", 1.0),
                        )
                        or 1.0
                    ),
                    "payload_height_capacity_m": float(
                        amr_type.get(
                            "payload_height_capacity_m",
                            amr_type.get("payload_size_capacity", 1.0),
                        )
                        or 1.0
                    ),
                }
            )
        return slots

    def _space_points_dimensions(self, points: list) -> Tuple[float, float]:
        if not points:
            return 0.0, 0.0

        xs = []
        ys = []
        for p in points:
            try:
                if "dx" in p and "dy" in p:
                    xs.append(float(p.get("dx", 0.0)))
                    ys.append(float(p.get("dy", 0.0)))
                else:
                    xs.append(float(p.get("x", 0.0)))
                    ys.append(float(p.get("y", 0.0)))
            except Exception:
                continue

        if not xs or not ys:
            return 0.0, 0.0

        return abs(max(xs) - min(xs)), abs(max(ys) - min(ys))

    def _payload_log_name(self, payload_name: str) -> str:
        return (
            ""
            if is_empty_payload_name(payload_name)
            else str(payload_name or "").strip()
        )

    def _payload_for_task(self, task: Task) -> Optional[PayloadType]:
        payload_name = str(getattr(task, "payload", "") or "").strip()
        if is_empty_payload_name(payload_name):
            return self.payloads.get(EMPTY_PAYLOAD_NAME)
        return self.payloads.get(payload_name)

    def _payload_prefers_multi_stop_amr(self, payload: Optional[PayloadType]) -> bool:
        if payload is None or is_empty_payload_name(payload.name):
            return False
        return bool(getattr(payload, "prefer_multi_stop_amr", False))

    def _task_prefers_multi_stop_amr(self, task: Task) -> bool:
        return self._payload_prefers_multi_stop_amr(self._payload_for_task(task))

    def _runtime_amr_payload_slots(self, amr: AMR) -> List[dict]:
        slots = getattr(amr, "payload_slots", None)
        clean = []
        if isinstance(slots, list):
            for index, slot in enumerate(slots, start=1):
                if not isinstance(slot, dict):
                    continue
                clean.append(
                    {
                        "name": str(slot.get("name", "")).strip() or f"Slot {index}",
                        "payload_capacity_kg": float(
                            slot.get("payload_capacity_kg", 0.0) or 0.0
                        ),
                        "payload_length_capacity_m": float(
                            slot.get("payload_length_capacity_m", 0.0) or 0.0
                        ),
                        "payload_width_capacity_m": float(
                            slot.get("payload_width_capacity_m", 0.0) or 0.0
                        ),
                        "payload_height_capacity_m": float(
                            slot.get("payload_height_capacity_m", 0.0) or 0.0
                        ),
                    }
                )
        if not clean:
            clean.append(
                {
                    "name": "Slot 1",
                    "payload_capacity_kg": float(
                        getattr(amr, "payload_capacity_kg", 0.0) or 0.0
                    ),
                    "payload_length_capacity_m": float(
                        getattr(amr, "payload_length_capacity_m", 0.0) or 0.0
                    ),
                    "payload_width_capacity_m": float(
                        getattr(amr, "payload_width_capacity_m", 0.0) or 0.0
                    ),
                    "payload_height_capacity_m": float(
                        getattr(amr, "payload_height_capacity_m", 0.0) or 0.0
                    ),
                }
            )
        return clean

    def _is_multi_stop_amr(self, amr: AMR) -> bool:
        slots = self._runtime_amr_payload_slots(amr)
        return bool(getattr(amr, "multi_stop_enabled", False)) and len(slots) > 1

    def _payload_fits_slot(self, payload: PayloadType, slot: dict) -> bool:
        return (
            float(payload.weight_kg)
            <= float(slot.get("payload_capacity_kg", 0.0) or 0.0)
            and float(payload.length_m)
            <= float(slot.get("payload_length_capacity_m", 0.0) or 0.0)
            and float(payload.width_m)
            <= float(slot.get("payload_width_capacity_m", 0.0) or 0.0)
            and float(payload.height_m)
            <= float(slot.get("payload_height_capacity_m", 0.0) or 0.0)
        )

    def _amr_can_carry_payload(self, amr: AMR, payload: PayloadType) -> bool:
        if is_empty_payload_name(payload.name):
            return True
        return any(
            self._payload_fits_slot(payload, slot)
            for slot in self._runtime_amr_payload_slots(amr)
        )

    def _assign_tasks_to_amr_slots(
        self, amr: AMR, tasks: List[Task]
    ) -> Optional[Dict[str, str]]:
        slots = self._runtime_amr_payload_slots(amr)
        used_slots = set()
        assignments: Dict[str, str] = {}
        sortable = []
        for task in tasks:
            payload = self._payload_for_task(task)
            if payload is None or is_empty_payload_name(payload.name):
                return None
            volume = (
                float(payload.length_m)
                * float(payload.width_m)
                * float(payload.height_m)
            )
            sortable.append((float(payload.weight_kg), volume, task.id, task, payload))
        for _weight, _volume, _task_id, task, payload in sorted(sortable, reverse=True):
            assigned = None
            for slot in slots:
                slot_name = str(slot.get("name", ""))
                if slot_name in used_slots:
                    continue
                if self._payload_fits_slot(payload, slot):
                    assigned = slot_name
                    break
            if assigned is None:
                return None
            assignments[task.id] = assigned
            used_slots.add(assigned)
        return assignments

    def _make_aggregate_payload(self, tasks: List[Task]) -> PayloadType:
        payloads = [self._payload_for_task(task) for task in tasks]
        payloads = [payload for payload in payloads if payload is not None]
        if not payloads:
            return self.payloads[EMPTY_PAYLOAD_NAME]
        return PayloadType(
            name="multi_payload",
            weight_kg=sum(float(payload.weight_kg) for payload in payloads),
            length_m=max(float(payload.length_m) for payload in payloads),
            width_m=max(float(payload.width_m) for payload in payloads),
            height_m=max(float(payload.height_m) for payload in payloads),
            size_units=sum(
                float(getattr(payload, "size_units", 0.0) or 0.0)
                for payload in payloads
            ),
        )

    def _multi_stop_task_is_eligible(self, task: Task) -> bool:
        if getattr(task, "is_idle_return", False) or getattr(
            task, "is_return_task", False
        ):
            return False
        if bool(getattr(task, "manual_task", False)) or bool(
            getattr(task, "manual_task_only", False)
        ):
            return False
        if task.release_time > self.current_time:
            return False
        if task.pickup not in self.locations or task.dropoff not in self.locations:
            return False
        payload = self._payload_for_task(task)
        if payload is None or is_empty_payload_name(payload.name):
            return False
        if not self._pickup_instance_available(task):
            self._set_task_pending_reason(
                task, self._pickup_instance_pending_reason(task)
            )
            return False
        if self._location_has_inventory_spaces(task.dropoff):
            if self._find_free_inventory_space(task.dropoff, payload) is None:
                self._set_task_pending_reason(
                    task, self._inventory_pending_reason(task.dropoff, payload)
                )
                return False
        return True

    def _multi_stop_batch_for_amr(self, amr: AMR) -> Optional[List[Task]]:
        if not self._is_multi_stop_amr(amr):
            return None
        slot_count = len(self._runtime_amr_payload_slots(amr))
        released = [
            item[3]
            for item in sorted(self.pending_tasks)
            if self._multi_stop_task_is_eligible(item[3])
        ]
        # Payloads marked as preferring multi-stop AMRs should get first access
        # to multi-stop slots, while the existing priority/release order is
        # retained inside each preference group.
        released.sort(
            key=lambda task: (
                0 if self._task_prefers_multi_stop_amr(task) else 1,
                int(getattr(task, "priority", 100) or 100),
                float(getattr(task, "release_time", 0.0) or 0.0),
                str(getattr(task, "id", "")),
            )
        )
        if len(released) < 2:
            return None
        selected: List[Task] = []
        route_signature = None
        for task in released[: max(12, slot_count * 3)]:
            # Keep a batch on the same route profile / dirty-label state so route restrictions stay predictable.
            signature = (
                str(getattr(task, "route_profile", "") or ""),
                bool("dirty" in list(getattr(task, "labels", []) or [])),
            )
            if route_signature is None:
                route_signature = signature
            if signature != route_signature:
                continue
            trial = selected + [task]
            if len(trial) > slot_count:
                continue
            if self._assign_tasks_to_amr_slots(amr, trial) is None:
                continue
            selected.append(task)
            if len(selected) >= slot_count:
                break
        return selected if len(selected) >= 2 else None

    def _estimate_route_seconds(
        self,
        amr: AMR,
        from_loc: Location,
        to_loc: Location,
        payload: PayloadType,
        rules: Optional[dict] = None,
        start_time_value: Optional[float] = None,
    ) -> float:
        if from_loc.floor == to_loc.floor:
            route = self._same_floor_segments(
                amr, from_loc, to_loc, rules=rules, start_time_value=start_time_value
            )
            return math.inf if route is None else float(route[1])
        plan = self._nearest_compatible_lift_plan(
            start_time_value if start_time_value is not None else self.current_time,
            amr,
            from_loc,
            to_loc,
            payload,
            rules=rules,
        )
        if plan is None:
            return math.inf
        return float(
            plan["final_finish"]
            - (start_time_value if start_time_value is not None else self.current_time)
        )

    def _ordered_multi_stop_legs(
        self,
        amr: AMR,
        tasks: List[Task],
        start_loc: Location,
        aggregate_payload: PayloadType,
        loaded_rules: Optional[dict],
        start_time_value: float,
    ) -> List[Tuple[str, Task]]:
        ordered: List[Tuple[str, Task]] = []
        current = start_loc
        t = start_time_value
        remaining = list(tasks)
        empty_payload = self.payloads.get(EMPTY_PAYLOAD_NAME, aggregate_payload)
        carrying = False
        while remaining:
            payload_for_leg = aggregate_payload if carrying else empty_payload
            rules = loaded_rules if carrying else None
            next_task = min(
                remaining,
                key=lambda task: self._estimate_route_seconds(
                    amr,
                    current,
                    self.locations[task.pickup],
                    payload_for_leg,
                    rules=rules,
                    start_time_value=t,
                ),
            )
            ordered.append(("pickup", next_task))
            t += self._estimate_route_seconds(
                amr,
                current,
                self.locations[next_task.pickup],
                payload_for_leg,
                rules=rules,
                start_time_value=t,
            )
            t += self.load_unload_time_sec
            current = self.locations[next_task.pickup]
            carrying = True
            remaining.remove(next_task)
        remaining = list(tasks)
        while remaining:
            next_task = min(
                remaining,
                key=lambda task: self._estimate_route_seconds(
                    amr,
                    current,
                    self.locations[task.dropoff],
                    aggregate_payload,
                    rules=loaded_rules,
                    start_time_value=t,
                ),
            )
            ordered.append(("dropoff", next_task))
            t += self._estimate_route_seconds(
                amr,
                current,
                self.locations[next_task.dropoff],
                aggregate_payload,
                rules=loaded_rules,
                start_time_value=t,
            )
            t += self.load_unload_time_sec
            current = self.locations[next_task.dropoff]
            remaining.remove(next_task)
        return ordered

    def _estimate_multi_stop_for_amr(
        self, amr: AMR, tasks: List[Task], reserve: bool = False
    ) -> Optional[dict]:
        try:
            if not tasks or len(tasks) < 2:
                return None
            slot_assignments = self._assign_tasks_to_amr_slots(amr, tasks)
            if slot_assignments is None:
                return None
            for task in tasks:
                payload = self._payload_for_task(task)
                if payload is None or not self._amr_can_carry_payload(amr, payload):
                    self._set_task_pending_reason(
                        task, "No AMR slot has sufficient payload weight/dimensions"
                    )
                    return None
                if not self._pickup_instance_available(task):
                    self._set_task_pending_reason(
                        task, self._pickup_instance_pending_reason(task)
                    )
                    return None
                if self._location_has_inventory_spaces(task.dropoff):
                    if self._find_free_inventory_space(task.dropoff, payload) is None:
                        self._set_task_pending_reason(
                            task, self._inventory_pending_reason(task.dropoff, payload)
                        )
                        return None

            aggregate_payload = self._make_aggregate_payload(tasks)
            empty_payload = self.payloads.get(EMPTY_PAYLOAD_NAME, aggregate_payload)
            amr_loc = self.locations[amr.location_name]
            loaded_rules = self._resolve_task_route_rules(tasks[0])
            t = max(
                self.current_time,
                amr.available_time,
                max(task.release_time for task in tasks),
            )
            task_start_time = t
            ordered_legs = self._ordered_multi_stop_legs(
                amr, tasks, amr_loc, aggregate_payload, loaded_rules, t
            )

            segments: List[dict] = []
            total = 0.0
            lift_energy_kwh_total = 0.0
            lift_empty_sec_total = 0.0
            lift_loaded_sec_total = 0.0
            travel_to_first_pickup_sec = 0.0
            loaded_travel_sec_total = 0.0
            current_location = amr_loc
            carrying_count = 0

            def move_between(
                location_a, location_b, current_time_value, payload_for_leg, rules=None
            ):
                nonlocal total, lift_energy_kwh_total, lift_empty_sec_total, lift_loaded_sec_total
                if location_a.floor == location_b.floor:
                    route = self._same_floor_segments(
                        amr,
                        location_a,
                        location_b,
                        rules=rules,
                        start_time_value=current_time_value,
                    )
                    if route is None:
                        return math.inf, None, 0.0, 0.0
                    same_segments, route_duration, route_distance = route
                    if reserve:
                        self._reserve_corridor_segments(
                            amr, same_segments, current_time_value
                        )
                    total += route_duration
                    return (
                        current_time_value + route_duration,
                        same_segments,
                        route_duration,
                        route_distance,
                    )

                plan = self._nearest_compatible_lift_plan(
                    current_time_value,
                    amr,
                    location_a,
                    location_b,
                    payload_for_leg,
                    rules=rules,
                )
                if plan is None:
                    return math.inf, None, 0.0, 0.0
                lift_energy_kwh_total += total_lift_energy_kwh(
                    lift=plan["lift"],
                    payload=payload_for_leg,
                    floor_height_m=self.floor_height_m,
                    reposition_floor_delta=(
                        plan["reposition_to_floor"] - plan["reposition_from_floor"]
                    ),
                    loaded_floor_delta=(location_b.floor - location_a.floor),
                    wait_time_sec=plan["wait_time"],
                    door_time_sec=plan["lift"].door_time_sec,
                )
                lift_empty_sec_total += float(plan.get("reposition_sec", 0.0))
                lift_loaded_sec_total += float(plan.get("loaded_travel_sec", 0.0))
                if reserve:
                    self._reserve_corridor_segments(
                        amr, plan["to_lift_segments"], current_time_value
                    )
                    self._reserve_corridor_segments(
                        amr, plan["from_lift_segments"], plan["lift_finish"]
                    )
                    plan["lift"].available_time = plan["lift_finish"]
                    plan["lift"].current_floor = location_b.floor
                    self._apply_lift_journey_wear(
                        plan["lift"],
                        journey_operating_sec=float(plan.get("reposition_sec", 0.0))
                        + float(plan.get("loaded_travel_sec", 0.0)),
                        journey_finish_time=plan["lift_finish"],
                    )
                transfer_segments = list(plan["to_lift_segments"])
                if plan["wait_time"] > 0:
                    transfer_segments.append(
                        {
                            "type": "wait_for_lift",
                            "lift_id": plan["lift"].id,
                            "from": plan["origin_lift"].name,
                            "to": plan["origin_lift"].name,
                            "duration": plan["wait_time"],
                            "distance_m": 0.0,
                        }
                    )
                if plan.get("reposition_sec", 0.0) > 0:
                    transfer_segments.append(
                        {
                            "type": "lift_reposition",
                            "lift_id": plan["lift"].id,
                            "from": f"{plan['lift'].id}-F{plan['reposition_from_floor']}",
                            "to": f"{plan['lift'].id}-F{plan['reposition_to_floor']}",
                            "from_floor": plan["reposition_from_floor"],
                            "to_floor": plan["reposition_to_floor"],
                            "wait_time": 0.0,
                            "duration": plan["reposition_sec"],
                            "distance_m": abs(
                                plan["reposition_to_floor"]
                                - plan["reposition_from_floor"]
                            )
                            * self.floor_height_m,
                            "vertical_distance_m": abs(
                                plan["reposition_to_floor"]
                                - plan["reposition_from_floor"]
                            )
                            * self.floor_height_m,
                        }
                    )
                transfer_segments.append(
                    {
                        "type": "lift_transfer",
                        "lift_id": plan["lift"].id,
                        "from": plan["origin_lift"].name,
                        "to": plan["destination_lift"].name,
                        "from_floor": location_a.floor,
                        "to_floor": location_b.floor,
                        "wait_time": 0.0,
                        "duration": plan["lift_finish"]
                        - plan["lift_start"]
                        - plan.get("reposition_sec", 0.0)
                        - plan["wait_time"],
                        "distance_m": plan["vertical_distance_m"],
                        "vertical_distance_m": plan["vertical_distance_m"],
                    }
                )
                transfer_segments.extend(plan["from_lift_segments"])
                segment_duration = plan["final_finish"] - current_time_value
                total += segment_duration
                return (
                    plan["final_finish"],
                    transfer_segments,
                    segment_duration,
                    (
                        plan["to_lift_distance_m"]
                        + plan["vertical_distance_m"]
                        + plan["from_lift_distance_m"]
                    ),
                )

            grouped_legs: List[Tuple[str, List[Task]]] = []
            idx = 0
            while idx < len(ordered_legs):
                action, task = ordered_legs[idx]
                if action == "pickup":
                    pickup_location_name = task.pickup
                    group = [task]
                    idx += 1
                    while idx < len(ordered_legs):
                        next_action, next_task = ordered_legs[idx]
                        if (
                            next_action != "pickup"
                            or next_task.pickup != pickup_location_name
                        ):
                            break
                        group.append(next_task)
                        idx += 1
                    grouped_legs.append(("pickup", group))
                    continue

                grouped_legs.append((action, [task]))
                idx += 1

            for action, leg_tasks in grouped_legs:
                task = leg_tasks[0]
                target_location = self.locations[
                    task.pickup if action == "pickup" else task.dropoff
                ]
                payload_for_leg = (
                    aggregate_payload if carrying_count > 0 else empty_payload
                )
                rules = loaded_rules if carrying_count > 0 else None
                t, new_segments, seg_time, _distance = move_between(
                    current_location, target_location, t, payload_for_leg, rules=rules
                )
                if new_segments is None or math.isinf(t):
                    return None
                if carrying_count == 0 and action == "pickup":
                    travel_to_first_pickup_sec += seg_time
                else:
                    loaded_travel_sec_total += seg_time
                for seg in new_segments:
                    seg.setdefault("multi_stop_task_ids", [x.id for x in tasks])
                    seg.setdefault("payload_slot_count", len(slot_assignments))
                segments.extend(new_segments)

                location_start = self._find_next_available_time(
                    target_location.name, t, self.load_unload_time_sec
                )
                location_wait = location_start - t
                if location_wait > 0:
                    segments.append(
                        {
                            "type": "wait_for_location",
                            "from": target_location.name,
                            "to": target_location.name,
                            "duration": location_wait,
                            "distance_m": 0.0,
                            "location": target_location.name,
                            "task_ids": [x.id for x in leg_tasks],
                            "multi_stop_task_ids": [x.id for x in tasks],
                        }
                    )
                    total += location_wait
                    t = location_start
                if reserve:
                    self._reserve_location(
                        target_location.name, t, t + self.load_unload_time_sec
                    )

                inventory_space_name = ""
                if action == "dropoff":
                    payload = self._payload_for_task(task)
                    if reserve and payload is not None:
                        reserved_space = self._reserve_inventory_space_for_task(
                            task, payload
                        )
                        if (
                            self._location_has_inventory_spaces(target_location.name)
                            and reserved_space is None
                        ):
                            self._set_task_pending_reason(
                                task,
                                self._inventory_pending_reason(
                                    target_location.name, payload
                                ),
                            )
                            return None
                        if reserved_space is not None:
                            inventory_space_name = str(reserved_space.get("name", ""))

                segment_task_ids = [x.id for x in leg_tasks]
                segments.append(
                    {
                        "type": action,
                        "location": target_location.name,
                        "duration": self.load_unload_time_sec,
                        "task_id": ",".join(segment_task_ids),
                        "task_ids": segment_task_ids,
                        "payload": ",".join(
                            str(getattr(x, "payload", "") or "") for x in leg_tasks
                        ),
                        "payload_instance_id": ",".join(
                            str(getattr(x, "payload_instance_id", "") or "")
                            for x in leg_tasks
                        ),
                        "slot_name": ",".join(
                            slot_assignments.get(x.id, "")
                            for x in leg_tasks
                            if slot_assignments.get(x.id, "")
                        ),
                        "inventory_space": inventory_space_name
                        or getattr(task, "assigned_inventory_space", ""),
                        "multi_stop_task_ids": [x.id for x in tasks],
                    }
                )
                t += self.load_unload_time_sec
                total += self.load_unload_time_sec
                current_location = target_location
                if action == "pickup":
                    carrying_count += len(leg_tasks)
                elif action == "dropoff":
                    carrying_count = max(0, carrying_count - len(leg_tasks))

            corridor_energy_kwh = total_route_energy_kwh(
                amr,
                aggregate_payload,
                travel_to_first_pickup_sec,
                loaded_travel_sec_total,
            )
            actual_energy_kwh = corridor_energy_kwh + lift_energy_kwh_total
            projected_battery_soc_after = (
                100.0
                * max(0.0, amr.battery_energy_kwh() - actual_energy_kwh)
                / max(amr.battery_capacity_kwh, 1e-9)
            )
            if requires_recharge_before_route(amr, actual_energy_kwh):
                return None
            if reserve:
                amr.consume_energy(actual_energy_kwh)
                battery_soc_after = amr.battery_soc_percent
            else:
                battery_soc_after = projected_battery_soc_after
            return {
                "multi_stop": True,
                "tasks": tasks,
                "task_start_time": task_start_time,
                "finish_time": t,
                "duration": total,
                "segments": segments,
                "end_location": current_location.name,
                "energy_kwh": actual_energy_kwh,
                "battery_soc_after": battery_soc_after,
                "corridor_energy_kwh": corridor_energy_kwh,
                "lift_energy_kwh": lift_energy_kwh_total,
                "lift_empty_sec_total": lift_empty_sec_total,
                "lift_loaded_sec_total": lift_loaded_sec_total,
                "slot_assignments": slot_assignments,
            }
        except Exception as exc:
            print(f"_estimate_multi_stop_for_amr failed for {amr.id}: {exc}")
            return None

    def _prepare_task_payload_instance(self, task: Task) -> None:
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        if not payload_name:
            task.payload = EMPTY_PAYLOAD_NAME
            task.payload_instance_id = ""
            return
        if payload_name not in self.payloads:
            return
        self.payload_instance_store.ensure_task_instance_id(task)

    def _task_requires_existing_payload_instance(self, task: Task) -> bool:
        # Outbound tasks can create a new physical object at their source.
        # Return tasks must collect the exact instance that the outbound task left
        # at the destination.
        return bool(getattr(task, "is_return_task", False))

    def _pickup_instance_available(self, task: Task) -> bool:
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        instance_id = str(getattr(task, "payload_instance_id", "") or "").strip()
        if not payload_name or not instance_id:
            return True
        if not self._task_requires_existing_payload_instance(task):
            return True
        return self.payload_instance_store.has_instance_at(
            task.pickup, instance_id, payload_name
        )

    def _pickup_instance_pending_reason(self, task: Task) -> str:
        instance_id = str(getattr(task, "payload_instance_id", "") or "").strip()
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        if instance_id:
            return (
                f"Payload instance {instance_id} ({payload_name}) is not available "
                f"at pickup location {task.pickup}"
            )
        return (
            f"Payload {payload_name} is not available at pickup location {task.pickup}"
        )

    def _pickup_payload_instance_for_task(self, task: Task) -> None:
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        if not payload_name:
            return

        instance_id = str(getattr(task, "payload_instance_id", "") or "").strip()
        record = None

        if instance_id:
            record = self.payload_instance_store.pickup(
                task.pickup,
                payload_name=payload_name,
                instance_id=instance_id,
            )
            if record is None and self._task_requires_existing_payload_instance(task):
                raise RuntimeError(self._pickup_instance_pending_reason(task))

        if record is None and not instance_id:
            # Normal outbound tasks can create a new physical object at the source.
            instance_id = self.payload_instance_store.ensure_task_instance_id(task)

        if instance_id:
            task.payload_instance_id = instance_id

    def _store_payload_instance_for_task(self, task: Task) -> None:
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        instance_id = str(getattr(task, "payload_instance_id", "") or "").strip()
        if not payload_name:
            return
        if not instance_id:
            instance_id = self.payload_instance_store.ensure_task_instance_id(task)
        self.payload_instance_store.store(
            task.dropoff,
            payload_name,
            instance_id,
            source_task_id=task.id,
            metadata={
                "task_source": getattr(task, "task_source", ""),
                "department_id": getattr(task, "department_id", ""),
                "container_type": getattr(task, "container_type", ""),
            },
        )

    def _init_inventory_spaces(self, location_dicts: List[dict]) -> None:
        self.inventory_spaces_by_location = {}

        for loc in location_dicts:
            location_name = str(loc.get("name", "")).strip()
            if not location_name:
                continue

            raw_spaces = loc.get("inventory_spaces", []) or []
            clean_spaces = []

            for index, raw_space in enumerate(raw_spaces, start=1):
                if not isinstance(raw_space, dict):
                    continue

                points = list(raw_space.get("points", []) or [])
                point_length, point_width = self._space_points_dimensions(points)

                length_m = float(
                    raw_space.get(
                        "length_m",
                        raw_space.get("length", point_length),
                    )
                    or point_length
                    or 0.0
                )
                width_m = float(
                    raw_space.get(
                        "width_m",
                        raw_space.get("width", point_width),
                    )
                    or point_width
                    or 0.0
                )
                height_m = float(
                    raw_space.get(
                        "height_m",
                        raw_space.get("height", 999999.0),
                    )
                    or 999999.0
                )

                name = str(raw_space.get("name", "")).strip() or f"Space {index}"
                occupied = bool(raw_space.get("occupied", False))

                clean_spaces.append(
                    {
                        "name": name,
                        "length_m": length_m,
                        "width_m": width_m,
                        "height_m": height_m,
                        "occupied": occupied,
                        "payload": str(raw_space.get("payload", "")).strip(),
                        "payload_instance_id": str(
                            raw_space.get("payload_instance_id", "")
                        ).strip(),
                        "reserved_by_task": str(
                            raw_space.get("reserved_by_task", "")
                        ).strip(),
                        "task_id": str(raw_space.get("task_id", "")).strip(),
                    }
                )

            if clean_spaces:
                self.inventory_spaces_by_location[location_name] = clean_spaces

    def _location_has_inventory_spaces(self, location_name: str) -> bool:
        # Inventory rules only apply where at least one valid inventory space has
        # been configured. No configured spaces means unlimited capacity.
        return bool(self.inventory_spaces_by_location.get(location_name, []))

    def _inventory_space_can_fit_payload(
        self, space: dict, payload: PayloadType
    ) -> bool:
        length_m = float(space.get("length_m", 0.0) or 0.0)
        width_m = float(space.get("width_m", 0.0) or 0.0)
        height_m = float(space.get("height_m", 999999.0) or 999999.0)

        # Allow the trolley/bin to be rotated in plan, but not laid on its side.
        fits_normal = payload.length_m <= length_m and payload.width_m <= width_m
        fits_rotated = payload.length_m <= width_m and payload.width_m <= length_m
        return (fits_normal or fits_rotated) and payload.height_m <= height_m

    def _find_free_inventory_space(
        self, location_name: str, payload: PayloadType
    ) -> Optional[dict]:
        for space in self.inventory_spaces_by_location.get(location_name, []):
            if bool(space.get("occupied", False)):
                continue
            if str(space.get("reserved_by_task", "")).strip():
                continue
            if not self._inventory_space_can_fit_payload(space, payload):
                continue
            return space
        return None

    def _inventory_pending_reason(
        self, location_name: str, payload: PayloadType
    ) -> str:
        spaces = self.inventory_spaces_by_location.get(location_name, [])
        if not spaces:
            return ""

        compatible_count = sum(
            1
            for space in spaces
            if self._inventory_space_can_fit_payload(space, payload)
        )
        if compatible_count <= 0:
            return (
                f"No compatible inventory space at {location_name} for payload "
                f"{payload.name} ({payload.length_m}m x {payload.width_m}m x {payload.height_m}m)"
            )

        return f"All compatible inventory spaces are full at {location_name}"

    def _reserve_inventory_space_for_task(
        self, task: Task, payload: PayloadType
    ) -> Optional[dict]:
        if not self._location_has_inventory_spaces(task.dropoff):
            return None

        space = self._find_free_inventory_space(task.dropoff, payload)
        if space is None:
            return None

        space["reserved_by_task"] = task.id
        task.assigned_inventory_space = str(space.get("name", ""))
        return space

    def _occupy_inventory_space_for_completed_task(
        self, task: Task, payload: PayloadType
    ) -> None:
        if not self._location_has_inventory_spaces(task.dropoff):
            return

        target_name = str(getattr(task, "assigned_inventory_space", "")).strip()
        spaces = self.inventory_spaces_by_location.get(task.dropoff, [])

        target_space = None
        for space in spaces:
            if target_name and str(space.get("name", "")) == target_name:
                target_space = space
                break

        if target_space is None:
            target_space = next(
                (
                    space
                    for space in spaces
                    if str(space.get("reserved_by_task", "")) == task.id
                ),
                None,
            )

        if target_space is None:
            target_space = self._find_free_inventory_space(task.dropoff, payload)

        if target_space is None:
            return

        target_space["occupied"] = True
        target_space["payload"] = payload.name
        target_space["payload_instance_id"] = str(
            getattr(task, "payload_instance_id", "") or ""
        )
        target_space["task_id"] = task.id
        target_space["reserved_by_task"] = ""
        task.assigned_inventory_space = str(target_space.get("name", ""))

    def _free_inventory_space_for_pickup(
        self, task: Task, payload: PayloadType
    ) -> None:
        if not self._location_has_inventory_spaces(task.pickup):
            return

        spaces = self.inventory_spaces_by_location.get(task.pickup, [])
        for space in spaces:
            if not bool(space.get("occupied", False)):
                continue
            stored_payload = str(space.get("payload", "")).strip()
            if stored_payload and stored_payload != payload.name:
                continue
            wanted_instance_id = str(
                getattr(task, "payload_instance_id", "") or ""
            ).strip()
            stored_instance_id = str(space.get("payload_instance_id", "") or "").strip()
            if (
                wanted_instance_id
                and stored_instance_id
                and wanted_instance_id != stored_instance_id
            ):
                continue
            space["occupied"] = False
            space["payload"] = ""
            space["payload_instance_id"] = ""
            space["task_id"] = ""
            space["reserved_by_task"] = ""
            return

    def _set_task_pending_reason(self, task: Optional[Task], reason: str) -> None:
        if task is None:
            return
        try:
            task.pending_reason = str(reason or "").strip()
        except Exception:
            pass

    def _task_tracking_log_kwargs(self, task: Optional[Task]) -> dict:
        if task is None:
            return {}
        return {
            "tracked_item_exchange": bool(
                getattr(task, "tracked_item_exchange", False)
            ),
            "exchange_mode": str(getattr(task, "exchange_mode", "") or ""),
            "tracked_item_source_payload": str(
                getattr(task, "tracked_item_source_payload", "") or ""
            ),
            "tracked_items": getattr(task, "tracked_items", {}) or {},
        }

    def _schedule_configured_return_task(self, task: Task, finish_time: float) -> None:
        if not bool(getattr(task, "return_enabled", False)):
            return

        return_payload = str(getattr(task, "return_payload", "") or "").strip()
        if not return_payload:
            return_payload = normalise_payload_name(getattr(task, "payload", ""))
        if not return_payload or return_payload not in self.payloads:
            return

        self.synthetic_task_counter += 1
        delay_sec = (
            max(0.0, float(getattr(task, "return_delay_minutes", 0.0) or 0.0)) * 60.0
        )
        return_task = Task(
            id=f"RETURN-{task.id}-{self.synthetic_task_counter}",
            pickup=task.dropoff,
            dropoff=task.pickup,
            payload=return_payload,
            release_time=finish_time + delay_sec,
            target_time=0.0,
            quantity=1,
            priority=int(
                getattr(task, "return_priority", 0) or getattr(task, "priority", 100)
            ),
            created_during_runtime=True,
            labels=list(getattr(task, "labels", []) or []) + ["return"],
            route_profile=(
                str(getattr(task, "return_route_profile", "") or "").strip() or None
            ),
            task_source="task_generation_return",
            department_id=str(getattr(task, "department_id", "") or ""),
            container_type=return_payload,
            payload_instance_id=str(getattr(task, "payload_instance_id", "") or ""),
            is_return_task=True,
        )
        self.schedule_task_release(return_task)

        pickup = self.locations.get(return_task.pickup)
        dropoff = self.locations.get(return_task.dropoff)
        self.log_step(
            event_time=return_task.release_time,
            event_type="return_task_generated",
            task_id=return_task.id,
            details=f"Generated delayed return for {task.id}",
            from_location=return_task.pickup,
            to_location=return_task.dropoff,
            payload_name=self._payload_log_name(return_task.payload),
            payload_instance_id=getattr(return_task, "payload_instance_id", ""),
            duration_sec=0.0,
            wait_time_sec=0.0,
            distance_m=0.0,
            start_time=return_task.release_time,
            end_time=return_task.release_time,
            start_node=return_task.pickup,
            end_node=return_task.dropoff,
            start_x=getattr(pickup, "x", None),
            start_y=getattr(pickup, "y", None),
            start_floor=getattr(pickup, "floor", None),
            end_x=getattr(dropoff, "x", None),
            end_y=getattr(dropoff, "y", None),
            end_floor=getattr(dropoff, "floor", None),
            status="generated",
            energy_kwh=0.0,
            task_source=return_task.task_source,
            department_id=return_task.department_id,
            container_type=return_payload,
        )

    def _fail_task(self, task: Task, reason: str, now: Optional[float] = None) -> None:
        reason = str(reason or "Task failed").strip()
        self._set_task_pending_reason(task, reason)
        self._remove_pending_task(task)

        task_id = str(getattr(task, "id", "")).strip()
        if task_id in self.failed_task_ids:
            return

        self.failed_task_ids.add(task_id)
        self.failed_tasks.append({"task_id": task.id, "reason": reason})
        event_time = self.current_time if now is None else now
        self.log_step(
            event_time=event_time,
            event_type="task_failed",
            task_id=task.id,
            details=reason,
            from_location=task.pickup,
            to_location=task.dropoff,
            payload_name=self._payload_log_name(task.payload),
            payload_instance_id=getattr(task, "payload_instance_id", ""),
            start_time=event_time,
            end_time=event_time,
            status="failed",
            task_source=getattr(task, "task_source", ""),
            department_id=getattr(task, "department_id", ""),
            waste_stream=getattr(task, "waste_stream", ""),
            waste_volume_m3=getattr(task, "waste_volume_m3", 0.0),
            container_type=getattr(task, "container_type", ""),
            pending_reason=reason,
        )

    def _rules_cache_key(
        self, rules: Optional[dict]
    ) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        if not rules:
            return ((), ())
        allowed_nodes = tuple(sorted(rules.get("allowed_nodes", set())))
        allowed_edges = tuple(sorted(rules.get("allowed_edges", set())))
        return (allowed_nodes, allowed_edges)

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
        rules = rules or self._empty_route_rules()
        cache_key = (floor, start_name, end_name, *self._rules_cache_key(rules))

        if start_name not in graph or end_name not in graph:
            self.route_cache[cache_key] = None
            return None

        if cache_key in self.route_cache:
            return self.route_cache[cache_key]

        if not self._node_allowed(start_name, rules):
            self.route_cache[cache_key] = None
            return None
        if not self._node_allowed(end_name, rules):
            self.route_cache[cache_key] = None
            return None

        heap = [(0.0, start_name)]
        best = {start_name: 0.0}
        prev: Dict[str, Tuple[str, float]] = {}

        while heap:
            dist, node = heapq.heappop(heap)
            if node == end_name:
                break
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
                    prev[nxt] = (node, edge["distance_m"])
                    heapq.heappush(heap, (new_dist, nxt))

        if end_name not in best:
            self.route_cache[cache_key] = None
            return None

        path_edges = []
        node = end_name
        while node != start_name:
            parent, distance_m = prev[node]
            path_edges.append(
                {
                    "from": parent,
                    "to": node,
                    "distance_m": distance_m,
                }
            )
            node = parent
        path_edges.reverse()

        result = {"distance_m": best[end_name], "edges": path_edges}
        self.route_cache[cache_key] = result
        return result

    def _find_next_available_time(
        self,
        location_name: str,
        requested_start: float,
        duration: float,
    ) -> float:
        max_concurrency = self.location_max_concurrency.get(location_name, 999999)
        reservations = self.location_reservations[location_name]

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
        reservations = self.location_reservations[location_name]
        item = (start_time, end_time)
        idx = len(reservations)
        while idx > 0 and reservations[idx - 1][0] > start_time:
            idx -= 1
        reservations.insert(idx, item)

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
        self._prepare_task_payload_instance(task)
        self.push_event(task.release_time, "task_release", {"task": task})

    def add_runtime_task(self, task_dict: dict):
        task_data = dict(task_dict)
        task_data["release_time"] = parse_release_time(
            task_data, self.clock.start_datetime
        )
        task_data.pop("release_datetime", None)
        task = Task(**task_data)
        task.created_during_runtime = True
        self._prepare_task_payload_instance(task)
        with self.lock:
            if task.release_time <= self.current_time:
                self._queue_pending_task(task)
                self._try_assign_tasks(self.current_time)
            else:
                self.schedule_task_release(task)

    def _init_department_runtime(self):
        self.department_runtime = {}

        for dept in self.departments:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                continue

            waste_stream_names = [
                str(x).strip()
                for x in dept.get("waste_streams", [])
                if str(x).strip() in self.waste_streams
            ]
            if not waste_stream_names:
                continue

            self.department_runtime[dept_id] = {}

            for stream_name in waste_stream_names:
                stream_cfg = dict(self.waste_streams.get(stream_name, {}))
                container_capacity_m3 = float(
                    stream_cfg.get("container_capacity_m3", 0.0) or 0.0
                )
                full_threshold_fraction = float(
                    stream_cfg.get("full_threshold_fraction", 0.8) or 0.8
                )

                self.department_runtime[dept_id][stream_name] = {
                    "last_update_time": 0.0,
                    "fill_m3": 0.0,
                    "generated_m3_total": 0.0,
                    "tasks_created": 0,
                    "container_capacity_m3": container_capacity_m3,
                    "full_threshold_fraction": full_threshold_fraction,
                }

    def _day_key_for_sim_time(self, sim_time_sec: float) -> str:
        dt = self.clock.sim_seconds_to_datetime(sim_time_sec)
        return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt.weekday()]

    def _department_is_active(self, dept: dict, sim_time_sec: float) -> bool:
        if not bool(dept.get("enabled", True)):
            return False

        active_days = dept.get("days_active", [])
        if active_days:
            if self._day_key_for_sim_time(sim_time_sec) not in set(active_days):
                return False

        hours_operated = float(dept.get("hours_operated_per_day", 24.0) or 0.0)
        if hours_operated <= 0:
            return False

        dt = self.clock.sim_seconds_to_datetime(sim_time_sec)
        hour_decimal = dt.hour + (dt.minute / 60.0) + (dt.second / 3600.0)
        return hour_decimal < hours_operated

    def _department_hourly_waste_rate_m3(
        self, dept: dict, sim_time_sec: float
    ) -> float:
        waste_cfg = dict(dept.get("waste", {}) or {})

        alpha = float(waste_cfg.get("alpha", 0.0) or 0.0)
        beta = float(waste_cfg.get("beta", 0.0) or 0.0)
        gamma = float(waste_cfg.get("gamma", 0.0) or 0.0)

        bed_count = float(dept.get("bed_count", 0.0) or 0.0)
        patient_turnover = float(dept.get("patient_turnover", 0.0) or 0.0)
        staff_count = float(dept.get("staff_count", 0.0) or 0.0)
        hours_operated = max(
            float(dept.get("hours_operated_per_day", 24.0) or 24.0), 1.0
        )

        # Turnover is assumed to be per active day, spread across operating hours
        turnover_per_hour = patient_turnover / hours_operated

        return (alpha * bed_count) + (beta * turnover_per_hour) + (gamma * staff_count)

    def _make_department_waste_task_id(self, dept_id: str, stream_name: str) -> str:
        self.department_task_counter += 1
        safe_stream = "".join(
            c if c.isalnum() else "_" for c in stream_name.upper()
        ).strip("_")
        return f"WASTE_{dept_id}_{safe_stream}_{self.department_task_counter:05d}"

    def _create_department_waste_task(
        self,
        dept: dict,
        stream_name: str,
        release_time: float,
        waste_volume_m3: float,
    ):
        dept_id = str(dept.get("id", "")).strip()
        dept_name = str(dept.get("name", dept_id)).strip()
        stream_cfg = dict(self.waste_streams.get(stream_name, {}))
        waste_cfg = dict(dept.get("waste", {}) or {})

        pickup_location = str(waste_cfg.get("pickup_location", "")).strip()
        dropoff_location = str(waste_cfg.get("dropoff_location", "")).strip()
        payload_name = str(stream_cfg.get("payload", "")).strip()

        if not pickup_location or pickup_location not in self.locations:
            return
        if not dropoff_location or dropoff_location not in self.locations:
            return
        if not payload_name or payload_name not in self.payloads:
            return

        task = Task(
            id=self._make_department_waste_task_id(dept_id, stream_name),
            pickup=pickup_location,
            dropoff=dropoff_location,
            payload=payload_name,
            release_time=release_time,
            target_time=0.0,
            quantity=1,
            priority=60,
            created_during_runtime=True,
            labels=["waste", stream_name],
            route_profile=None,
            task_source="department_waste",
            department_id=dept_id,
            waste_stream=stream_name,
            waste_volume_m3=float(waste_volume_m3),
            container_type=payload_name,
        )

        self.schedule_task_release(task)

        self.log_step(
            event_time=release_time,
            event_type="waste_task_generated",
            task_id=task.id,
            details=f"Generated waste collection for {dept_name} / {stream_name}",
            from_location=pickup_location,
            to_location=dropoff_location,
            payload_name=payload_name,
            duration_sec=0.0,
            wait_time_sec=0.0,
            distance_m=0.0,
            start_time=release_time,
            end_time=release_time,
            start_node=pickup_location,
            end_node=dropoff_location,
            start_x=self.locations[pickup_location].x,
            start_y=self.locations[pickup_location].y,
            start_floor=self.locations[pickup_location].floor,
            end_x=self.locations[dropoff_location].x,
            end_y=self.locations[dropoff_location].y,
            end_floor=self.locations[dropoff_location].floor,
            status="generated",
            energy_kwh=0.0,
            task_source="department_waste",
            department_id=dept_id,
            waste_stream=stream_name,
            waste_volume_m3=float(waste_volume_m3),
            container_type=payload_name,
        )

    def _update_department_waste_until(self, now: float):
        if now <= 0 or not self.departments:
            return

        for dept in self.departments:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                continue
            runtime_by_stream = self.department_runtime.get(dept_id, {})
            if not runtime_by_stream:
                continue

            for stream_name, runtime in runtime_by_stream.items():
                last_time = float(runtime.get("last_update_time", 0.0) or 0.0)
                if now <= last_time:
                    continue

                if self._department_is_active(dept, now):
                    elapsed_hours = (now - last_time) / 3600.0
                    hourly_rate = self._department_hourly_waste_rate_m3(dept, now)
                    generated_m3 = max(0.0, elapsed_hours * hourly_rate)

                    runtime["fill_m3"] += generated_m3
                    runtime["generated_m3_total"] += generated_m3

                    container_capacity_m3 = float(
                        runtime.get("container_capacity_m3", 0.0) or 0.0
                    )
                    full_threshold_fraction = float(
                        runtime.get("full_threshold_fraction", 0.8) or 0.8
                    )
                    trigger_volume_m3 = container_capacity_m3 * full_threshold_fraction

                    if trigger_volume_m3 > 0:
                        while runtime["fill_m3"] >= trigger_volume_m3:
                            self._create_department_waste_task(
                                dept=dept,
                                stream_name=stream_name,
                                release_time=now,
                                waste_volume_m3=trigger_volume_m3,
                            )
                            runtime["fill_m3"] -= trigger_volume_m3
                            runtime["tasks_created"] += 1

                runtime["last_update_time"] = now

    def _queue_pending_task(self, task: Task):
        self.pending_task_counter += 1
        heapq.heappush(
            self.pending_tasks,
            (task.priority, task.release_time, self.pending_task_counter, task),
        )

    def _distance_same_floor(self, a: Location, b: Location) -> float:
        return math.hypot(b.x - a.x, b.y - a.y)

    def _physical_edge_key(self, a_name: str, b_name: str) -> Tuple[str, str]:
        # Same physical corridor edge in either direction.
        return tuple(sorted((a_name, b_name)))

    def _spacing_time_sec(self, amr: AMR) -> float:
        return self.amr_spacing_m / max(amr.speed_m_per_sec, 1e-9)

    def _edge_recent_demand(self, edge_key: Tuple[str, str], t: float) -> int:
        reservations = self.edge_reservations.get(edge_key, [])
        window = self.edge_congestion_window_sec
        count = 0
        for start, end, _ in reservations:
            if start <= t + window and end >= t - window:
                count += 1
        return count

    def _find_next_edge_start(
        self,
        edge_key: Tuple[str, str],
        requested_start: float,
        duration: float,
        spacing_time: float,
    ) -> Tuple[float, int]:
        reservations = self.edge_reservations.get(edge_key, [])
        t = requested_start

        while True:
            overlap_count = 0
            next_candidate = None

            for start, end, _ in reservations:
                protected_start = start - spacing_time
                protected_end = end + spacing_time

                if not (t + duration <= protected_start or t >= protected_end):
                    overlap_count += 1
                    if next_candidate is None or protected_end < next_candidate:
                        next_candidate = protected_end

            if overlap_count < self.edge_max_concurrency:
                return t, overlap_count

            if next_candidate is None:
                return t, overlap_count

            t = next_candidate

    def _reserve_edge(
        self,
        from_name: str,
        to_name: str,
        start_time: float,
        end_time: float,
        amr_id: str,
    ):
        edge_key = self._physical_edge_key(from_name, to_name)
        reservations = self.edge_reservations[edge_key]
        item = (start_time, end_time, amr_id)
        idx = len(reservations)
        while idx > 0 and reservations[idx - 1][0] > start_time:
            idx -= 1
        reservations.insert(idx, item)

    def _reserve_node(
        self,
        node_name: str,
        start_time: float,
        end_time: float,
        amr_id: str,
    ):
        self.node_reservations[node_name].append((start_time, end_time, amr_id))

    def _find_next_node_arrival(
        self,
        node_name: str,
        requested_arrival: float,
        spacing_time: float,
    ) -> float:
        reservations = sorted(self.node_reservations.get(node_name, []))
        t = requested_arrival

        while True:
            blocked = False
            next_candidate = None

            for start, end, _ in reservations:
                protected_start = start - spacing_time
                protected_end = end + spacing_time

                if protected_start <= t < protected_end:
                    blocked = True
                    if next_candidate is None or protected_end < next_candidate:
                        next_candidate = protected_end

            if not blocked:
                return t

            if next_candidate is None:
                return t

            t = next_candidate

    def _reserve_corridor_segments(
        self,
        amr: AMR,
        segments: List[dict],
        start_time: float,
    ):
        t = start_time
        spacing_time = self._spacing_time_sec(amr)

        for segment in segments:
            duration = float(segment.get("duration", 0.0))
            seg_type = segment.get("type", "")

            if seg_type == "corridor":
                self._reserve_edge(
                    segment["from"],
                    segment["to"],
                    t,
                    t + duration,
                    amr.id,
                )
                self._reserve_node(
                    segment["to"],
                    t + duration,
                    t + duration + self.node_clearance_time_sec,
                    amr.id,
                )

            elif seg_type in {"wait_for_edge", "wait_for_node"}:
                node_name = segment.get("from") or segment.get("to")
                if node_name:
                    self._reserve_node(
                        node_name,
                        t,
                        t + duration,
                        amr.id,
                    )

            t += duration

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
        start_time_value: Optional[float] = None,
    ) -> Optional[Tuple[List[dict], float, float]]:
        route = self._shortest_path_same_floor(
            start.floor,
            start.name,
            end.name,
            rules=rules,
        )
        if route is None:
            return None

        segments: List[dict] = []
        total_duration = 0.0
        current_time_value = start_time_value

        for edge in route["edges"]:
            base_duration = edge["distance_m"] / max(amr.speed_m_per_sec, 1e-9)

            if current_time_value is None:
                duration = base_duration
                speed_factor = 1.0
                congestion_count = 0
                edge_wait = 0.0
                node_wait = 0.0
            else:
                edge_key = self._physical_edge_key(edge["from"], edge["to"])
                congestion_count = self._edge_recent_demand(
                    edge_key, current_time_value
                )

                speed_factor = max(
                    self.min_congestion_speed_factor,
                    1.0 - (congestion_count * self.edge_slowdown_per_amr),
                )

                # Start with a slowed-but-moving duration
                travel_duration = base_duration / max(speed_factor, 1e-9)

                edge_start, _ = self._find_next_edge_start(
                    edge_key=edge_key,
                    requested_start=current_time_value,
                    duration=travel_duration,
                    spacing_time=self._spacing_time_sec(amr),
                )
                edge_wait = max(0.0, edge_start - current_time_value)

                if edge_wait > 0:
                    segments.append(
                        {
                            "type": "wait_for_edge",
                            "from": edge["from"],
                            "to": edge["from"],
                            "duration": edge_wait,
                            "distance_m": 0.0,
                            "congestion_count": congestion_count,
                        }
                    )
                    total_duration += edge_wait
                    current_time_value = edge_start

                proposed_arrival = current_time_value + travel_duration
                safe_arrival = self._find_next_node_arrival(
                    edge["to"],
                    proposed_arrival,
                    self._spacing_time_sec(amr),
                )

                node_wait = max(0.0, safe_arrival - proposed_arrival)

                if node_wait > 0:
                    # First try to absorb delay by slowing down on the segment
                    adjusted_duration = travel_duration + node_wait
                    effective_speed_factor = base_duration / max(
                        adjusted_duration, 1e-9
                    )

                    if effective_speed_factor >= self.min_congestion_speed_factor:
                        duration = adjusted_duration
                    else:
                        duration = base_duration / max(
                            self.min_congestion_speed_factor, 1e-9
                        )
                        stop_wait = max(
                            0.0, safe_arrival - (current_time_value + duration)
                        )
                        if stop_wait > 0:
                            segments.append(
                                {
                                    "type": "wait_for_node",
                                    "from": edge["to"],
                                    "to": edge["to"],
                                    "duration": stop_wait,
                                    "distance_m": 0.0,
                                    "congestion_count": congestion_count,
                                }
                            )
                            total_duration += stop_wait
                        node_wait = stop_wait
                        speed_factor = self.min_congestion_speed_factor
                else:
                    duration = travel_duration

            segments.append(
                {
                    "type": "corridor",
                    "from": edge["from"],
                    "to": edge["to"],
                    "duration": duration,
                    "distance_m": edge["distance_m"],
                    "speed_factor": speed_factor,
                    "congestion_count": congestion_count,
                }
            )
            total_duration += duration

            if current_time_value is not None:
                current_time_value += duration + node_wait

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
            if not lift.can_fit(payload, amr):
                continue

            origin_lift = self._lift_location_on_floor(lift, from_loc.floor)
            destination_lift = self._lift_location_on_floor(lift, to_loc.floor)

            if not self._node_allowed(origin_lift.name, rules):
                continue
            if not self._node_allowed(destination_lift.name, rules):
                continue

            ##
            to_lift_route = self._same_floor_segments(
                amr,
                from_loc,
                origin_lift,
                rules=rules,
                start_time_value=ready_time,
            )
            if to_lift_route is None:
                continue

            to_lift_segments, to_lift_sec, to_lift_distance_m = to_lift_route

            arrival_at_lift = ready_time + to_lift_sec
            lift_start = max(arrival_at_lift, lift.available_time)

            reposition_sec = abs(lift.current_floor - from_loc.floor) / max(
                lift.speed_floors_per_sec, 1e-9
            )
            loaded_travel_sec = abs(to_loc.floor - from_loc.floor) / max(
                lift.speed_floors_per_sec, 1e-9
            )

            reposition_start = max(arrival_at_lift, lift.available_time)
            reposition_finish = reposition_start + reposition_sec

            board_start = reposition_finish
            loaded_start = board_start + lift.door_time_sec + lift.boarding_time_sec
            loaded_finish = loaded_start + loaded_travel_sec
            unload_finish = loaded_finish + lift.door_time_sec + lift.boarding_time_sec

            lift_start = reposition_start
            lift_finish = unload_finish

            from_lift_route = self._same_floor_segments(
                amr,
                destination_lift,
                to_loc,
                rules=rules,
                start_time_value=lift_finish,
            )
            if from_lift_route is None:
                continue

            from_lift_segments, from_lift_sec, from_lift_distance_m = from_lift_route
            final_finish = lift_finish + from_lift_sec

            ##

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
                    "reposition_from_floor": lift.current_floor,
                    "reposition_to_floor": from_loc.floor,
                    "reposition_sec": reposition_sec,
                    "loaded_travel_sec": loaded_travel_sec,
                    "reposition_start": reposition_start,
                    "reposition_finish": reposition_finish,
                    "loaded_start": loaded_start,
                    "loaded_finish": loaded_finish,
                }

        return best_plan

    def _charge_location_candidates(self) -> List[Location]:
        candidates = []
        for name in self.charge_location_names:
            if name in self.locations:
                candidates.append(self.locations[name])
        if not candidates and self.charge_location_name in self.locations:
            candidates.append(self.locations[self.charge_location_name])
        return candidates

    def _select_charge_location_for_amr(
        self, amr: AMR, current_loc: Location, now: float
    ) -> Optional[Location]:
        candidates = self._charge_location_candidates()
        if not candidates:
            return None
        best_loc = None
        best_finish = math.inf
        dummy_payload = (
            next(iter(self.payloads.values()))
            if self.payloads
            else PayloadType("empty", 0.0)
        )
        for charge_loc in candidates:
            if current_loc.floor == charge_loc.floor:
                route = self._same_floor_segments(amr, current_loc, charge_loc)
                if route is None:
                    continue
                finish = now + route[1]
            else:
                plan = self._nearest_compatible_lift_plan(
                    now, amr, current_loc, charge_loc, dummy_payload
                )
                if plan is None:
                    continue
                finish = plan["final_finish"]
            if finish < best_finish:
                best_finish = finish
                best_loc = charge_loc
        return best_loc

    def _apply_lift_journey_wear(
        self,
        lift: Lift,
        journey_operating_sec: float = 0.0,
        journey_finish_time: Optional[float] = None,
    ) -> None:
        lift.apply_journey_wear()
        lift.operating_time_since_failure_sec += max(
            0.0, float(journey_operating_sec or 0.0)
        )

        mtbf_sec = (
            max(0.0, float(lift.mean_time_between_failures_hours or 0.0)) * 3600.0
        )
        if mtbf_sec <= 0.0:
            return
        if lift.operating_time_since_failure_sec < mtbf_sec:
            return

        repair_sec = max(0.0, float(lift.mean_time_to_repair_hours or 0.0)) * 3600.0
        start_repair = max(
            float(lift.available_time),
            float(journey_finish_time or lift.available_time),
        )
        lift.failed_until = start_repair + repair_sec
        lift.available_time = max(lift.available_time, lift.failed_until)
        lift.failures_count += 1
        lift.operating_time_since_failure_sec = 0.0

    def _plan_return_to_charge(
        self,
        amr: AMR,
        current_loc: Location,
        current_time_value: float,
        reserve: bool = False,
    ) -> Optional[dict]:
        charge_loc = self._select_charge_location_for_amr(
            amr, current_loc, current_time_value
        )
        if charge_loc is None:
            return None
        self.charge_location_name = charge_loc.name

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

        if plan["wait_time"] > 0:
            transfer_segments.append(
                {
                    "type": "wait_for_lift",
                    "lift_id": plan["lift"].id,
                    "from": plan["origin_lift"].name,
                    "to": plan["origin_lift"].name,
                    "duration": plan["wait_time"],
                    "distance_m": 0.0,
                }
            )

        if plan.get("reposition_sec", 0.0) > 0:
            transfer_segments.append(
                {
                    "type": "lift_reposition",
                    "lift_id": plan["lift"].id,
                    "from": f"{plan['lift'].id}-F{plan['reposition_from_floor']}",
                    "to": f"{plan['lift'].id}-F{plan['reposition_to_floor']}",
                    "from_floor": plan["reposition_from_floor"],
                    "to_floor": plan["reposition_to_floor"],
                    "wait_time": 0.0,
                    "duration": plan["reposition_sec"],
                    "distance_m": abs(
                        plan["reposition_to_floor"] - plan["reposition_from_floor"]
                    )
                    * self.floor_height_m,
                    "vertical_distance_m": abs(
                        plan["reposition_to_floor"] - plan["reposition_from_floor"]
                    )
                    * self.floor_height_m,
                }
            )

        transfer_segments.append(
            {
                "type": "lift_transfer",
                "lift_id": plan["lift"].id,
                "from": plan["origin_lift"].name,
                "to": plan["destination_lift"].name,
                "from_floor": current_loc.floor,
                "to_floor": charge_loc.floor,
                "wait_time": 0.0,
                "duration": (
                    plan["lift_finish"]
                    - plan["lift_start"]
                    - plan.get("reposition_sec", 0.0)
                    - plan["wait_time"]
                ),
                "distance_m": plan["vertical_distance_m"],
                "vertical_distance_m": plan["vertical_distance_m"],
            }
        )

        transfer_segments.extend(plan["from_lift_segments"])

        if reserve:
            plan["lift"].available_time = plan["lift_finish"]
            plan["lift"].current_floor = charge_loc.floor
            self._apply_lift_journey_wear(
                plan["lift"],
                journey_operating_sec=float(plan.get("reposition_sec", 0.0))
                + float(plan.get("loaded_travel_sec", 0.0)),
                journey_finish_time=plan["lift_finish"],
            )
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
            next_event_time = self.events[0].time
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
            if getattr(task, "is_idle_return", False):
                if getattr(task, "amr_id", "") != amr.id:
                    return None
            if task.pickup not in self.locations or task.dropoff not in self.locations:
                return None

            payload = self._payload_for_task(task)
            if payload is None:
                return None

            if not self._pickup_instance_available(task):
                self._set_task_pending_reason(
                    task, self._pickup_instance_pending_reason(task)
                )
                return None
            if not self._amr_can_carry_payload(amr, payload):
                self._set_task_pending_reason(
                    task, "No AMR has sufficient payload weight/dimensions"
                )
                return None

            if self._location_has_inventory_spaces(task.dropoff):
                free_space = self._find_free_inventory_space(task.dropoff, payload)
                if free_space is None:
                    self._set_task_pending_reason(
                        task,
                        self._inventory_pending_reason(task.dropoff, payload),
                    )
                    return None

            amr_loc = self.locations[amr.location_name]
            pickup_loc = self.locations[task.pickup]
            dropoff_loc = self.locations[task.dropoff]

            lift_energy_kwh_total = 0.0

            # No restrictions before pickup
            pre_pickup_rules = None

            # Apply route profile only once the load has been picked up
            loaded_route_rules = self._resolve_task_route_rules(task)

            to_pickup_est = (
                self._same_floor_segments(
                    amr, amr_loc, pickup_loc, rules=pre_pickup_rules
                )
                if amr_loc.floor == pickup_loc.floor
                else None
            )
            loaded_est = (
                self._same_floor_segments(
                    amr, pickup_loc, dropoff_loc, rules=loaded_route_rules
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
            task_start_time = t

            total = sum(seg["duration"] for seg in charge_segments)
            segments = list(charge_segments)
            current_location = amr_loc

            lift_empty_sec_total = 0.0
            lift_loaded_sec_total = 0.0

            def move_between(
                location_a: Location,
                location_b: Location,
                current_time_value: float,
                rules: Optional[dict] = None,
            ) -> Tuple[float, Location, Optional[List[dict]], float]:
                nonlocal total

                if location_a.floor == location_b.floor:
                    route = self._same_floor_segments(
                        amr,
                        location_a,
                        location_b,
                        rules=rules,
                        start_time_value=current_time_value,
                    )
                    if route is None:
                        return math.inf, location_b, None, 0.0

                    same_segments, route_duration, _ = route
                    total += route_duration

                    if reserve:
                        self._reserve_corridor_segments(
                            amr=amr,
                            segments=same_segments,
                            start_time=current_time_value,
                        )

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
                    rules=rules,
                )
                if plan is None:
                    return math.inf, location_b, None, 0.0

                nonlocal lift_energy_kwh_total
                lift_energy_kwh_total += total_lift_energy_kwh(
                    lift=plan["lift"],
                    payload=payload,
                    floor_height_m=self.floor_height_m,
                    reposition_floor_delta=(
                        plan["reposition_to_floor"] - plan["reposition_from_floor"]
                    ),
                    loaded_floor_delta=(location_b.floor - location_a.floor),
                    wait_time_sec=plan["wait_time"],
                    door_time_sec=plan["lift"].door_time_sec,
                )

                segment_duration = plan["final_finish"] - current_time_value
                total += segment_duration

                nonlocal lift_empty_sec_total, lift_loaded_sec_total
                lift_empty_sec_total += float(plan.get("reposition_sec", 0.0))
                lift_loaded_sec_total += float(plan.get("loaded_travel_sec", 0.0))

                if reserve:
                    self._reserve_corridor_segments(
                        amr=amr,
                        segments=plan["to_lift_segments"],
                        start_time=current_time_value,
                    )
                    self._reserve_corridor_segments(
                        amr=amr,
                        segments=plan["from_lift_segments"],
                        start_time=plan["lift_finish"],
                    )
                    plan["lift"].available_time = plan["lift_finish"]
                    plan["lift"].current_floor = location_b.floor
                    self._apply_lift_journey_wear(
                        plan["lift"],
                        journey_operating_sec=float(plan.get("reposition_sec", 0.0))
                        + float(plan.get("loaded_travel_sec", 0.0)),
                        journey_finish_time=plan["lift_finish"],
                    )

                transfer_segments = list(plan["to_lift_segments"])

                if plan["wait_time"] > 0:
                    transfer_segments.append(
                        {
                            "type": "wait_for_lift",
                            "lift_id": plan["lift"].id,
                            "from": plan["origin_lift"].name,
                            "to": plan["origin_lift"].name,
                            "duration": plan["wait_time"],
                            "distance_m": 0.0,
                        }
                    )

                if plan.get("reposition_sec", 0.0) > 0:
                    transfer_segments.append(
                        {
                            "type": "lift_reposition",
                            "lift_id": plan["lift"].id,
                            "from": f"{plan['lift'].id}-F{plan['reposition_from_floor']}",
                            "to": f"{plan['lift'].id}-F{plan['reposition_to_floor']}",
                            "from_floor": plan["reposition_from_floor"],
                            "to_floor": plan["reposition_to_floor"],
                            "wait_time": 0.0,
                            "duration": plan["reposition_sec"],
                            "distance_m": abs(
                                plan["reposition_to_floor"]
                                - plan["reposition_from_floor"]
                            )
                            * self.floor_height_m,
                            "vertical_distance_m": abs(
                                plan["reposition_to_floor"]
                                - plan["reposition_from_floor"]
                            )
                            * self.floor_height_m,
                            "energy_kwh": total_lift_energy_kwh(
                                lift=plan["lift"],
                                payload=payload,
                                floor_height_m=self.floor_height_m,
                                reposition_floor_delta=(
                                    plan["reposition_to_floor"]
                                    - plan["reposition_from_floor"]
                                ),
                                loaded_floor_delta=0,
                                wait_time_sec=0.0,
                                door_time_sec=0.0,
                            ),
                        }
                    )

                transfer_segments.append(
                    {
                        "type": "lift_transfer",
                        "lift_id": plan["lift"].id,
                        "from": plan["origin_lift"].name,
                        "to": plan["destination_lift"].name,
                        "from_floor": location_a.floor,
                        "to_floor": location_b.floor,
                        "wait_time": 0.0,
                        "duration": (
                            plan["lift_finish"]
                            - plan["lift_start"]
                            - plan.get("reposition_sec", 0.0)
                            - plan["wait_time"]
                        ),
                        "distance_m": plan["vertical_distance_m"],
                        "vertical_distance_m": plan["vertical_distance_m"],
                        "energy_kwh": total_lift_energy_kwh(
                            lift=plan["lift"],
                            payload=payload,
                            floor_height_m=self.floor_height_m,
                            reposition_floor_delta=0,
                            loaded_floor_delta=(location_b.floor - location_a.floor),
                            wait_time_sec=plan["wait_time"],
                            door_time_sec=plan["lift"].door_time_sec,
                        ),
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
                current_location, pickup_loc, t, rules=pre_pickup_rules
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
                current_location, dropoff_loc, t, rules=loaded_route_rules
            )
            if new_segments is None or math.isinf(t):
                return None
            loaded_travel_sec += seg_time
            segments.extend(new_segments)

            # ... keep the rest of the function unchanged
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

            inventory_space_name = ""
            if reserve:
                self._reserve_location(
                    dropoff_loc.name,
                    t,
                    t + self.load_unload_time_sec,
                )
                reserved_space = self._reserve_inventory_space_for_task(task, payload)
                if (
                    self._location_has_inventory_spaces(dropoff_loc.name)
                    and reserved_space is None
                ):
                    self._set_task_pending_reason(
                        task,
                        self._inventory_pending_reason(dropoff_loc.name, payload),
                    )
                    return None
                if reserved_space is not None:
                    inventory_space_name = str(reserved_space.get("name", ""))

            t += self.load_unload_time_sec
            total += self.load_unload_time_sec
            segments.append(
                {
                    "type": "dropoff",
                    "location": dropoff_loc.name,
                    "duration": self.load_unload_time_sec,
                    "inventory_space": inventory_space_name
                    or getattr(task, "assigned_inventory_space", ""),
                }
            )

            corridor_energy_kwh = total_route_energy_kwh(
                amr, payload, travel_to_pickup_sec, loaded_travel_sec
            )

            lift_energy_kwh = lift_energy_kwh_total

            actual_energy_kwh = corridor_energy_kwh + lift_energy_kwh

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
                "task_start_time": task_start_time,
                "finish_time": t,
                "duration": total,
                "segments": segments,
                "end_location": end_location_name,
                "energy_kwh": actual_energy_kwh,
                "battery_soc_after": battery_soc_after,
                "corridor_energy_kwh": corridor_energy_kwh,
                "lift_energy_kwh": lift_energy_kwh,
                "lift_empty_sec_total": lift_empty_sec_total,
                "lift_loaded_sec_total": lift_loaded_sec_total,
            }
        except Exception as exc:
            print(f"_estimate_task_for_amr failed for {task.id} on {amr.id}: {exc}")
            return None

    def _select_best_assignment(self) -> Optional[Tuple[AMR, Task, dict]]:
        if not self.pending_tasks:
            return None

        best = None
        best_finish = math.inf
        multi_stop_best = None
        multi_stop_best_finish = math.inf

        candidate_tasks = []
        for item in self.pending_tasks[: min(8, len(self.pending_tasks))]:
            candidate_tasks.append(item)

        for amr in self.amrs:
            if getattr(amr, "is_charging", False):
                continue
            if self._needs_post_task_recharge(amr):
                continue
            batch = self._multi_stop_batch_for_amr(amr)
            if not batch:
                continue
            estimate = self._estimate_multi_stop_for_amr(amr, batch, reserve=False)
            if estimate is None:
                continue
            finish_time = estimate["finish_time"]
            if finish_time < multi_stop_best_finish:
                multi_stop_best_finish = finish_time
                multi_stop_best = (amr, batch, estimate)

        # Multi-stop is a route-shape preference, not just a quickest-finish
        # estimate.  If a feasible batch exists, commit it before comparing
        # against single-task assignments; otherwise the first nearby task can
        # win on finish time and make the AMR return to the same pickup location
        # repeatedly.
        if multi_stop_best is not None:
            return multi_stop_best

        for _, _, _, task in candidate_tasks:
            if task.release_time > self.current_time:
                self._set_task_pending_reason(task, "Waiting for release time")
                continue

            payload_for_inventory = self._payload_for_task(task)
            if (
                payload_for_inventory is not None
                and self._location_has_inventory_spaces(task.dropoff)
            ):
                payload = payload_for_inventory
                if self._find_free_inventory_space(task.dropoff, payload) is None:
                    self._set_task_pending_reason(
                        task,
                        self._inventory_pending_reason(task.dropoff, payload),
                    )
                    continue

            task_prefers_multi_stop = self._task_prefers_multi_stop_amr(task)
            task_best = None
            task_best_finish = math.inf
            preferred_task_best = None
            preferred_task_best_finish = math.inf

            for amr in self.amrs:
                if getattr(amr, "is_charging", False):
                    continue

                if self._needs_post_task_recharge(amr):
                    continue

                estimate = self._estimate_task_for_amr(amr, task, reserve=False)
                if estimate is None:
                    continue

                finish_time = estimate["finish_time"]
                if finish_time < task_best_finish:
                    task_best_finish = finish_time
                    task_best = (amr, task, estimate)

                if task_prefers_multi_stop and self._is_multi_stop_amr(amr):
                    if finish_time < preferred_task_best_finish:
                        preferred_task_best_finish = finish_time
                        preferred_task_best = (amr, task, estimate)

            # If this payload prefers multi-stop AMRs and at least one compatible
            # multi-stop AMR can perform the task, use that AMR even if a
            # single-slot AMR would finish slightly earlier. If no multi-stop
            # AMR is feasible, fall back to the normal best assignment.
            chosen_for_task = preferred_task_best or task_best
            chosen_finish = (
                preferred_task_best_finish
                if preferred_task_best is not None
                else task_best_finish
            )

            if chosen_for_task is not None and chosen_finish < best_finish:
                best_finish = chosen_finish
                best = chosen_for_task

        return best

    def _remove_pending_task(self, target_task: Task):
        rebuilt = []
        target_id = str(getattr(target_task, "id", "")).strip()
        while self.pending_tasks:
            item = heapq.heappop(self.pending_tasks)
            item_id = str(getattr(item[3], "id", "")).strip()
            if item_id == target_id:
                continue
            rebuilt.append(item)
        for item in rebuilt:
            heapq.heappush(self.pending_tasks, item)

    # Task Runner - steps thru sequentially until task end

    def _try_assign_tasks(self, now: float):
        self.current_time = max(self.current_time, now)
        self._queue_idle_return_tasks(self.current_time)

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

            # Return trip to home location
            self._queue_idle_return_tasks(self.current_time)

            choice = self._select_best_assignment()
            if choice is None:
                failed_inventory_task = False
                for _priority, _release, _counter, pending_task in list(
                    self.pending_tasks
                ):
                    if pending_task.release_time > self.current_time:
                        continue
                    payload = self._payload_for_task(pending_task)
                    if payload is None:
                        continue
                    if not self._location_has_inventory_spaces(pending_task.dropoff):
                        continue
                    if (
                        self._find_free_inventory_space(pending_task.dropoff, payload)
                        is None
                    ):
                        self._fail_task(
                            pending_task,
                            self._inventory_pending_reason(
                                pending_task.dropoff, payload
                            ),
                            now=self.current_time,
                        )
                        failed_inventory_task = True
                        break
                if failed_inventory_task:
                    continue
                self._create_wait_event_for_pending_tasks(self.current_time)
                return

            amr, task_or_tasks, _ = choice

            if isinstance(task_or_tasks, list):
                tasks = task_or_tasks
                committed = self._estimate_multi_stop_for_amr(amr, tasks, reserve=True)

                if committed is None:
                    for failed_task in tasks:
                        reason = (
                            getattr(failed_task, "pending_reason", "")
                            or "No feasible multi-stop AMR/lift/battery/graph combination"
                        )
                        self._fail_task(failed_task, reason, now=self.current_time)
                    continue

                for multi_task in tasks:
                    self._remove_pending_task(multi_task)
                    self._set_task_pending_reason(multi_task, "")

                start_time = committed["task_start_time"]
                finish_time = committed["finish_time"]
                previous_location = amr.location_name
                amr.total_busy_time += committed["duration"]
                amr.available_time = finish_time
                amr.location_name = committed["end_location"]
                amr.completed_tasks += len(tasks)

                for multi_task in tasks:
                    self.log_step(
                        event_time=start_time,
                        event_type="multi_stop_task_assigned",
                        task_id=multi_task.id,
                        amr_id=amr.id,
                        details=(
                            f"Assigned multi-stop batch to {amr.id}; "
                            f"slot={committed.get('slot_assignments', {}).get(multi_task.id, '')}; "
                            f"batch={','.join(task.id for task in tasks)}"
                        ),
                        from_location=multi_task.pickup,
                        to_location=multi_task.dropoff,
                        payload_name=self._payload_log_name(multi_task.payload),
                        payload_instance_id=getattr(
                            multi_task, "payload_instance_id", ""
                        ),
                        task_duration_sec=committed["duration"],
                        amr_location_before=previous_location,
                        amr_location_after=committed["end_location"],
                        start_time=start_time,
                        end_time=start_time + 1.0,
                        status="start",
                        task_source=getattr(multi_task, "task_source", ""),
                        department_id=getattr(multi_task, "department_id", ""),
                        waste_stream=getattr(multi_task, "waste_stream", ""),
                        waste_volume_m3=getattr(multi_task, "waste_volume_m3", 0.0),
                        container_type=getattr(multi_task, "container_type", ""),
                        **self._task_tracking_log_kwargs(multi_task),
                    )

                self._log_multi_stop_segments(amr, tasks, committed, start_time)

                self.push_event(
                    finish_time,
                    "multi_stop_complete",
                    {
                        "tasks": tasks,
                        "amr_id": amr.id,
                        "start_time": start_time,
                        "finish_time": finish_time,
                        "duration": committed["duration"],
                        "segments": committed["segments"],
                        "end_location": committed.get(
                            "end_location", amr.location_name
                        ),
                        "energy_kwh": committed["energy_kwh"],
                        "battery_soc_after": amr.battery_soc_percent,
                        "lift_energy_kwh": committed["lift_energy_kwh"],
                        "lift_empty_sec_total": committed["lift_empty_sec_total"],
                        "lift_loaded_sec_total": committed["lift_loaded_sec_total"],
                        "slot_assignments": committed.get("slot_assignments", {}),
                    },
                )
                continue

            task = task_or_tasks
            committed = self._estimate_task_for_amr(amr, task, reserve=True)

            if committed is None:
                reason = (
                    getattr(task, "pending_reason", "")
                    or "No feasible AMR/lift/battery/graph combination"
                )
                self._fail_task(task, reason, now=self.current_time)
                continue

            self._remove_pending_task(task)
            self._set_task_pending_reason(task, "")
            start_time = committed["task_start_time"]
            finish_time = committed["finish_time"]
            previous_location = amr.location_name
            amr.total_busy_time += committed["duration"]
            amr.available_time = finish_time
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
                payload_name=self._payload_log_name(task.payload),
                payload_instance_id=getattr(task, "payload_instance_id", ""),
                task_duration_sec=committed["duration"],
                amr_location_before=previous_location,
                amr_location_after=committed["end_location"],
                start_time=start_time,
                end_time=start_time + 1.0,
                status="start",
                task_source=getattr(task, "task_source", ""),
                department_id=getattr(task, "department_id", ""),
                waste_stream=getattr(task, "waste_stream", ""),
                waste_volume_m3=getattr(task, "waste_volume_m3", 0.0),
                container_type=getattr(task, "container_type", ""),
                **self._task_tracking_log_kwargs(task),
            )

            segment_start_time = start_time
            carrying_payload = False

            for segment in committed["segments"]:
                from_node = segment.get("from", "")
                to_node = segment.get("to", "")

                lift_id = segment.get("lift_id", "")
                if not lift_id and segment.get("type", "").startswith("lift_"):
                    for key_node in (from_node, to_node):
                        if key_node:
                            for lift in self.lifts:
                                prefix = f"{lift.id}-F"
                                if key_node.startswith(prefix):
                                    lift_id = lift.id
                                    break
                            if lift_id:
                                break

                from_coords = self.graph_nodes.get(from_node)
                to_coords = self.graph_nodes.get(to_node)

                wait_time = float(segment.get("wait_time", 0.0))
                duration = float(segment.get("duration", 0.0))
                segment_type = segment.get("type", "")
                segment_has_payload = (
                    carrying_payload
                    or segment_type in {"pickup", "dropoff"}
                    or bool(
                        getattr(task, "is_return_task", False)
                        and segment_type not in {"wait_for_location"}
                    )
                )
                segment_payload_name = task.payload if segment_has_payload else ""
                segment_payload_instance_id = (
                    getattr(task, "payload_instance_id", "")
                    if segment_has_payload
                    else ""
                )

                explicit_wait = duration if segment_type.startswith("wait_") else 0.0

                if wait_time > 0:
                    self.log_step(
                        event_time=segment_start_time,
                        event_type="segment_wait",
                        task_id=task.id,
                        amr_id=amr.id,
                        details=json.dumps(segment, ensure_ascii=False),
                        from_location=from_node or task.pickup,
                        to_location=to_node or task.dropoff,
                        payload_name=segment_payload_name,
                        payload_instance_id=segment_payload_instance_id,
                        lift_id=lift_id,
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
                        energy_kwh=segment.get("energy_kwh", 0.0),
                    )
                    segment_start_time += wait_time

                if explicit_wait > 0:
                    self.log_step(
                        event_time=segment_start_time,
                        event_type="segment_wait",
                        task_id=task.id,
                        amr_id=amr.id,
                        details=json.dumps(segment, ensure_ascii=False),
                        from_location=from_node or task.pickup,
                        to_location=to_node or task.dropoff,
                        payload_name=segment_payload_name,
                        payload_instance_id=segment_payload_instance_id,
                        lift_id=lift_id,
                        duration_sec=explicit_wait,
                        wait_time_sec=explicit_wait,
                        distance_m=0.0,
                        segment_type=segment_type,
                        start_time=segment_start_time,
                        end_time=segment_start_time + explicit_wait,
                        start_node=from_node,
                        end_node=to_node or from_node,
                        start_x=getattr(from_coords, "x", None),
                        start_y=getattr(from_coords, "y", None),
                        start_floor=getattr(from_coords, "floor", None),
                        end_x=getattr(to_coords, "x", None),
                        end_y=getattr(to_coords, "y", None),
                        end_floor=getattr(to_coords, "floor", None),
                        status="waiting",
                        energy_kwh=segment.get("energy_kwh", 0.0),
                    )

                if explicit_wait > 0:
                    segment_start_time += explicit_wait
                    continue

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
                    payload_name=segment_payload_name,
                    payload_instance_id=segment_payload_instance_id,
                    lift_id=lift_id,
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
                    energy_kwh=segment.get("energy_kwh", 0.0),
                )

                segment_start_time = segment_end_time
                if segment_type == "pickup":
                    carrying_payload = True
                elif segment_type == "dropoff":
                    carrying_payload = False

            self.push_event(
                finish_time,
                "task_complete",
                {
                    "task": task,
                    "amr_id": amr.id,
                    "start_time": start_time,
                    "finish_time": finish_time,
                    "duration": committed["duration"],
                    "target_time": task.target_time,
                    "segments": committed["segments"],
                    "energy_kwh": committed["energy_kwh"],
                    "battery_soc_after": amr.battery_soc_percent,
                    "lift_energy_kwh": committed["lift_energy_kwh"],
                    "lift_empty_sec_total": committed["lift_empty_sec_total"],
                    "lift_loaded_sec_total": committed["lift_loaded_sec_total"],
                },
            )

    def _log_multi_stop_segments(
        self, amr: AMR, tasks: List[Task], committed: dict, start_time: float
    ) -> None:
        """Write visualiser-friendly rows for a committed multi-stop route.

        The visualiser needs the complete AMR slot/onboard state on every row,
        not just the payload associated with the current segment.  This logger
        therefore writes grouped pickup/dropoff rows and repeats the current
        onboard state across all movement, wait and lift rows.
        """
        tasks_by_id = {str(task.id): task for task in tasks}
        fallback_task = tasks[0] if tasks else None
        slot_assignments = committed.get("slot_assignments", {}) or {}
        all_task_ids = [str(task.id) for task in tasks]
        segment_start_time = start_time
        carrying_task_ids = set()

        def _task_ids_for_segment(segment: dict) -> List[str]:
            raw_ids = segment.get("task_ids")
            if isinstance(raw_ids, list):
                ids = [str(x).strip() for x in raw_ids if str(x).strip()]
                if ids:
                    return ids

            raw_id = str(segment.get("task_id", "") or "").strip()
            if raw_id:
                ids = [x.strip() for x in raw_id.split(",") if x.strip()]
                if ids:
                    return ids

            return []

        def _payload_name_for_ids(task_ids: List[str]) -> str:
            names = []
            for task_id in task_ids:
                task = tasks_by_id.get(task_id)
                if task is None:
                    continue
                payload_name = self._payload_log_name(getattr(task, "payload", ""))
                if payload_name:
                    names.append(payload_name)
            return ",".join(names)

        def _payload_instance_for_ids(task_ids: List[str]) -> str:
            values = []
            for task_id in task_ids:
                task = tasks_by_id.get(task_id)
                if task is None:
                    continue
                value = str(getattr(task, "payload_instance_id", "") or "").strip()
                if value:
                    values.append(value)
            return ",".join(values)

        def _payload_slot_for_ids(task_ids: List[str]) -> str:
            values = []
            for task_id in task_ids:
                value = str(slot_assignments.get(task_id, "") or "").strip()
                if value:
                    values.append(value)
            return ",".join(values)

        def _onboard_payload_records(task_ids) -> List[dict]:
            records = []
            for task_id in sorted(str(x) for x in task_ids):
                task = tasks_by_id.get(task_id)
                if task is None:
                    continue
                payload_name = self._payload_log_name(getattr(task, "payload", ""))
                if not payload_name:
                    continue
                slot_name = str(slot_assignments.get(task_id, "") or "").strip()
                records.append(
                    {
                        "task_id": task_id,
                        "payload": payload_name,
                        "payload_instance_id": str(
                            getattr(task, "payload_instance_id", "") or ""
                        ).strip(),
                        "pickup": str(getattr(task, "pickup", "") or "").strip(),
                        "dropoff": str(getattr(task, "dropoff", "") or "").strip(),
                        "slot_name": slot_name,
                    }
                )
            return records

        def _onboard_slot_records(task_ids) -> List[dict]:
            records = []
            for item in _onboard_payload_records(task_ids):
                records.append(
                    {
                        "slot_name": item.get("slot_name", ""),
                        "task_id": item.get("task_id", ""),
                        "payload": item.get("payload", ""),
                        "payload_instance_id": item.get("payload_instance_id", ""),
                    }
                )
            return records

        for segment in committed["segments"]:
            segment_type = str(segment.get("type", "") or "").strip()
            segment_task_ids = _task_ids_for_segment(segment)
            task = (
                tasks_by_id.get(segment_task_ids[0])
                if segment_task_ids
                else fallback_task
            )

            from_node = segment.get("from", "") or segment.get("location", "")
            to_node = segment.get("to", "") or segment.get("location", "")
            from_coords = self.graph_nodes.get(from_node)
            to_coords = self.graph_nodes.get(to_node)
            lift_id = segment.get("lift_id", "")
            if not lift_id and segment_type.startswith("lift_"):
                for key_node in (from_node, to_node):
                    if key_node:
                        for lift in self.lifts:
                            prefix = f"{lift.id}-F"
                            if key_node.startswith(prefix):
                                lift_id = lift.id
                                break
                        if lift_id:
                            break

            duration = float(segment.get("duration", 0.0) or 0.0)
            wait_time = float(segment.get("wait_time", 0.0) or 0.0)
            explicit_wait = duration if segment_type.startswith("wait_") else 0.0
            segment_end_time = segment_start_time + duration

            # For pickup/dropoff rows, publish the onboard state AFTER the load
            # action.  For movement/wait/lift rows, publish the state carried
            # through the segment.  This makes slot occupancy persist during
            # travel in the visualiser.
            onboard_after = set(carrying_task_ids)
            if segment_type == "pickup":
                onboard_after.update(segment_task_ids)
            elif segment_type == "dropoff":
                for task_id in segment_task_ids:
                    onboard_after.discard(task_id)

            visible_task_ids = segment_task_ids or sorted(carrying_task_ids)
            segment_task_id = ",".join(visible_task_ids)
            segment_payload_name = _payload_name_for_ids(visible_task_ids)
            segment_payload_instance_id = _payload_instance_for_ids(visible_task_ids)
            segment_payload_slot = _payload_slot_for_ids(visible_task_ids)

            self.log_step(
                event_time=segment_start_time,
                event_type=f"multi_stop_segment_{segment_type}",
                task_id=segment_task_id or (task.id if task is not None else ""),
                amr_id=amr.id,
                details=json.dumps(segment, ensure_ascii=False),
                from_location=from_node or (task.pickup if task is not None else ""),
                to_location=to_node or (task.dropoff if task is not None else ""),
                payload_name=segment_payload_name,
                payload_instance_id=segment_payload_instance_id,
                payload_slot=segment_payload_slot,
                onboard_payloads=_onboard_payload_records(onboard_after),
                onboard_slots=_onboard_slot_records(onboard_after),
                multi_stop_task_ids=all_task_ids,
                multi_stop_pickup_count=(
                    len(segment_task_ids) if segment_type == "pickup" else 0
                ),
                multi_stop_dropoff_count=(
                    len(segment_task_ids) if segment_type == "dropoff" else 0
                ),
                lift_id=lift_id,
                duration_sec=duration,
                wait_time_sec=wait_time or explicit_wait,
                distance_m=segment.get("distance_m", 0.0),
                segment_type=segment_type,
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
                status="waiting" if segment_type.startswith("wait_") else "completed",
                energy_kwh=segment.get("energy_kwh", 0.0),
                task_source=(
                    getattr(task, "task_source", "") if task is not None else ""
                ),
                department_id=(
                    getattr(task, "department_id", "") if task is not None else ""
                ),
                waste_stream=(
                    getattr(task, "waste_stream", "") if task is not None else ""
                ),
                waste_volume_m3=(
                    getattr(task, "waste_volume_m3", 0.0) if task is not None else 0.0
                ),
                container_type=(
                    getattr(task, "container_type", "") if task is not None else ""
                ),
            )

            carrying_task_ids = onboard_after
            segment_start_time = segment_end_time

    def _update_task_generators_until(self, now: float):
        if not getattr(self, "task_generation_manager", None):
            return
        if now > getattr(self, "task_generation_horizon_sec", now):
            return

        for record in self.task_generation_manager.update_until(now):
            task = record.task
            self.schedule_task_release(task)

            pickup = self.locations.get(record.pickup_location)
            dropoff = self.locations.get(record.dropoff_location)

            self.log_step(
                event_time=task.release_time,
                event_type=record.event_type,
                task_id=task.id,
                details=record.details,
                from_location=record.pickup_location,
                to_location=record.dropoff_location,
                payload_name=self._payload_log_name(record.payload_name),
                payload_instance_id=getattr(task, "payload_instance_id", ""),
                duration_sec=0.0,
                wait_time_sec=0.0,
                distance_m=0.0,
                start_time=task.release_time,
                end_time=task.release_time,
                start_node=record.pickup_location,
                end_node=record.dropoff_location,
                start_x=getattr(pickup, "x", None),
                start_y=getattr(pickup, "y", None),
                start_floor=getattr(pickup, "floor", None),
                end_x=getattr(dropoff, "x", None),
                end_y=getattr(dropoff, "y", None),
                end_floor=getattr(dropoff, "floor", None),
                status="generated",
                energy_kwh=0.0,
                task_source=record.task_source,
                department_id=record.department_id,
                waste_stream=record.waste_stream,
                waste_volume_m3=record.waste_volume_m3,
                container_type=record.container_type,
                **self._task_tracking_log_kwargs(task),
            )

    def run(self):
        self.wall_start_time = time.time()

        while True:
            with self.lock:
                if not self.events:
                    break

                event = heapq.heappop(self.events)
                self._update_task_generators_until(event.time)
                self.current_time = max(self.current_time, event.time)
                self._handle_event(event)

            self._print_progress()

            if self.stop_requested:
                break

        self._print_progress_complete()
        self.print_short_summary()
        print()

    def _queue_same_time_task_releases(self, event: Event) -> List[Task]:
        """Queue the current task release and all other releases at the same
        simulation time before trying to assign work.

        Generated multi-stop workloads often create several tasks with the same
        release timestamp.  Assigning after the first release lets a single task
        win before the rest of the batch has reached pending_tasks.
        """
        released_tasks: List[Task] = []

        task = event.payload.get("task")
        if task is not None:
            self._queue_pending_task(task)
            released_tasks.append(task)

        deferred_event = None
        while self.events:
            next_event = heapq.heappop(self.events)
            if (
                next_event.event_type == "task_release"
                and abs(float(next_event.time) - float(event.time)) <= 1e-9
            ):
                next_task = next_event.payload.get("task")
                if next_task is not None:
                    self._queue_pending_task(next_task)
                    released_tasks.append(next_task)
                continue

            deferred_event = next_event
            break

        if deferred_event is not None:
            heapq.heappush(self.events, deferred_event)

        return released_tasks

    def _handle_event(self, event: Event):
        if event.event_type == "task_release":
            self._queue_same_time_task_releases(event)
            self._try_assign_tasks(event.time)
        elif event.event_type == "task_complete":
            task: Task = event.payload["task"]
            payload_obj = self._payload_for_task(task)
            if payload_obj is not None and not is_empty_payload_name(task.payload):
                try:
                    self._pickup_payload_instance_for_task(task)
                except RuntimeError as exc:
                    self._fail_task(task, str(exc), now=event.payload["finish_time"])
                    return
                self._free_inventory_space_for_pickup(task, payload_obj)
                self._store_payload_instance_for_task(task)
                self._occupy_inventory_space_for_completed_task(task, payload_obj)
            self.log_step(
                event_time=event.payload["finish_time"],
                event_type="task_complete",
                task_id=task.id,
                amr_id=event.payload["amr_id"],
                details=f"Task {task.id} completed",
                from_location=task.pickup,
                to_location=task.dropoff,
                payload_name=self._payload_log_name(task.payload),
                payload_instance_id=getattr(task, "payload_instance_id", ""),
                duration_sec=0.0,
                wait_time_sec=0.0,
                distance_m=0.0,
                start_time=event.payload["finish_time"],
                end_time=event.payload["finish_time"],
                status="finish",
                task_source=getattr(task, "task_source", ""),
                department_id=getattr(task, "department_id", ""),
                waste_stream=getattr(task, "waste_stream", ""),
                waste_volume_m3=getattr(task, "waste_volume_m3", 0.0),
                container_type=getattr(task, "container_type", ""),
            )

            self.completed_task_records.append(
                {
                    "task_id": task.id,
                    "pickup": task.pickup,
                    "dropoff": task.dropoff,
                    "payload": self._payload_log_name(task.payload),
                    "payload_instance_id": getattr(task, "payload_instance_id", ""),
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
                    "lift_energy_kwh": round(
                        event.payload.get("lift_energy_kwh", 0.0), 4
                    ),
                    "lift_empty_sec_total": round(
                        event.payload.get("lift_empty_sec_total", 0.0), 3
                    ),
                    "lift_loaded_sec_total": round(
                        event.payload.get("lift_loaded_sec_total", 0.0), 3
                    ),
                    "tracked_item_exchange": bool(
                        getattr(task, "tracked_item_exchange", False)
                    ),
                    "exchange_mode": str(getattr(task, "exchange_mode", "") or ""),
                    "tracked_item_source_payload": str(
                        getattr(task, "tracked_item_source_payload", "") or ""
                    ),
                    "tracked_items": getattr(task, "tracked_items", {}) or {},
                }
            )

            self._schedule_configured_return_task(task, event.payload["finish_time"])

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

        elif event.event_type == "multi_stop_complete":
            tasks: List[Task] = event.payload["tasks"]
            for task in tasks:
                payload_obj = self._payload_for_task(task)
                if payload_obj is not None and not is_empty_payload_name(task.payload):
                    try:
                        self._pickup_payload_instance_for_task(task)
                    except RuntimeError as exc:
                        self._fail_task(
                            task, str(exc), now=event.payload["finish_time"]
                        )
                        continue
                    self._free_inventory_space_for_pickup(task, payload_obj)
                    self._store_payload_instance_for_task(task)
                    self._occupy_inventory_space_for_completed_task(task, payload_obj)

                final_location_name = str(
                    event.payload.get("end_location") or task.dropoff or ""
                )
                final_location = self.locations.get(final_location_name)

                self.log_step(
                    event_time=event.payload["finish_time"],
                    event_type="multi_stop_task_complete",
                    task_id=task.id,
                    amr_id=event.payload["amr_id"],
                    details=(
                        f"Task {task.id} completed as part of a multi-stop route; "
                        f"planned_origin={task.pickup}; planned_destination={task.dropoff}; "
                        f"amr_final_location={final_location_name}"
                    ),
                    from_location=final_location_name,
                    to_location=final_location_name,
                    payload_name=self._payload_log_name(task.payload),
                    payload_instance_id=getattr(task, "payload_instance_id", ""),
                    duration_sec=0.0,
                    wait_time_sec=0.0,
                    distance_m=0.0,
                    start_time=event.payload["finish_time"],
                    end_time=event.payload["finish_time"],
                    start_node=final_location_name,
                    end_node=final_location_name,
                    start_x=getattr(final_location, "x", None),
                    start_y=getattr(final_location, "y", None),
                    start_floor=getattr(final_location, "floor", None),
                    end_x=getattr(final_location, "x", None),
                    end_y=getattr(final_location, "y", None),
                    end_floor=getattr(final_location, "floor", None),
                    status="finish",
                    task_source=getattr(task, "task_source", ""),
                    department_id=getattr(task, "department_id", ""),
                    waste_stream=getattr(task, "waste_stream", ""),
                    waste_volume_m3=getattr(task, "waste_volume_m3", 0.0),
                    container_type=getattr(task, "container_type", ""),
                )

                self.completed_task_records.append(
                    {
                        "task_id": task.id,
                        "pickup": task.pickup,
                        "dropoff": task.dropoff,
                        "payload": self._payload_log_name(task.payload),
                        "payload_instance_id": getattr(task, "payload_instance_id", ""),
                        "amr_id": event.payload["amr_id"],
                        "start_datetime": self.clock.format_sim_time(
                            event.payload["start_time"]
                        ),
                        "finish_datetime": self.clock.format_sim_time(
                            event.payload["finish_time"]
                        ),
                        "duration_hms": format_duration(event.payload["duration"]),
                        "target_duration_hms": (
                            format_duration(task.target_time)
                            if getattr(task, "target_time", 0.0) > 0
                            else ""
                        ),
                        "overrun": (
                            event.payload["duration"]
                            > getattr(task, "target_time", 0.0)
                            if getattr(task, "target_time", 0.0) > 0
                            else False
                        ),
                        "overrun_sec": (
                            round(event.payload["duration"] - task.target_time, 3)
                            if getattr(task, "target_time", 0.0) > 0
                            and event.payload["duration"] > task.target_time
                            else 0.0
                        ),
                        "energy_kwh": round(event.payload["energy_kwh"], 4),
                        "battery_soc_after": round(
                            event.payload["battery_soc_after"], 2
                        ),
                        "segments": event.payload["segments"],
                        "lift_energy_kwh": round(
                            event.payload.get("lift_energy_kwh", 0.0), 4
                        ),
                        "lift_empty_sec_total": round(
                            event.payload.get("lift_empty_sec_total", 0.0), 3
                        ),
                        "lift_loaded_sec_total": round(
                            event.payload.get("lift_loaded_sec_total", 0.0), 3
                        ),
                        "multi_stop": True,
                        "payload_slot": event.payload.get("slot_assignments", {}).get(
                            task.id, ""
                        ),
                        "tracked_item_exchange": bool(
                            getattr(task, "tracked_item_exchange", False)
                        ),
                        "exchange_mode": str(getattr(task, "exchange_mode", "") or ""),
                        "tracked_item_source_payload": str(
                            getattr(task, "tracked_item_source_payload", "") or ""
                        ),
                        "tracked_items": getattr(task, "tracked_items", {}) or {},
                    }
                )
                self._schedule_configured_return_task(
                    task, event.payload["finish_time"]
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
                energy_kwh=0.0,
            )
            self._try_assign_tasks(event.time)

        elif event.event_type == "generator_tick":
            next_tick = event.time + max(60.0, self.task_generation_interval_sec)
            if next_tick <= self.task_generation_horizon_sec:
                self.push_event(next_tick, "generator_tick", {})
            self._try_assign_tasks(event.time)

        elif event.event_type == "charge_cycle_start":
            amr = next(a for a in self.amrs if a.id == event.payload["amr_id"])
            segment_start_time = event.time

            for segment in event.payload["travel_segments"]:
                from_node = segment.get("from", "")
                to_node = segment.get("to", "")

                lift_id = segment.get("lift_id", "")
                if not lift_id and segment.get("type", "").startswith("lift_"):
                    for key_node in (from_node, to_node):
                        if key_node:
                            for lift in self.lifts:
                                prefix = f"{lift.id}-F"
                                if key_node.startswith(prefix):
                                    lift_id = lift.id
                                    break
                            if lift_id:
                                break

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
                    lift_id=lift_id,
                    start_x=getattr(from_coords, "x", None),
                    start_y=getattr(from_coords, "y", None),
                    start_floor=getattr(from_coords, "floor", None),
                    end_x=getattr(to_coords, "x", None),
                    end_y=getattr(to_coords, "y", None),
                    end_floor=getattr(to_coords, "floor", None),
                    status="completed",
                    energy_kwh=segment.get("energy_kwh", 0.0),
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
                energy_kwh=0.0,
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
                energy_kwh=0.0,
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
                payload_name=self._payload_log_name(task.payload),
                payload_instance_id=getattr(task, "payload_instance_id", ""),
                duration_sec=event.payload["actual_duration"],
                task_duration_sec=event.payload["target_time"],
                status="overrun",
            )

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
        payload_instance_id: str = "",
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
        energy_kwh: float = 0.0,
        task_source: str = "",
        department_id: str = "",
        waste_stream: str = "",
        waste_volume_m3: float = 0.0,
        container_type: str = "",
        pending_reason: str = "",
        payload_slot: str = "",
        onboard_payloads=None,
        onboard_slots=None,
        multi_stop_task_ids=None,
        multi_stop_pickup_count: int = 0,
        multi_stop_dropoff_count: int = 0,
        tracked_item_exchange: bool = False,
        exchange_mode: str = "",
        tracked_item_source_payload: str = "",
        tracked_items: Optional[dict] = None,
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
                "payload": self._payload_log_name(payload_name),
                "payload_instance_id": payload_instance_id,
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
                "energy_kwh": energy_kwh,
                "task_source": task_source,
                "department_id": department_id,
                "waste_stream": waste_stream,
                "waste_volume_m3": round(float(waste_volume_m3 or 0.0), 6),
                "container_type": container_type,
                "pending_reason": pending_reason,
                "payload_slot": payload_slot,
                "onboard_payloads": json.dumps(
                    onboard_payloads or [], ensure_ascii=False
                ),
                "onboard_slots": json.dumps(onboard_slots or [], ensure_ascii=False),
                "multi_stop_task_ids": json.dumps(
                    multi_stop_task_ids or [], ensure_ascii=False
                ),
                "multi_stop_pickup_count": int(multi_stop_pickup_count or 0),
                "multi_stop_dropoff_count": int(multi_stop_dropoff_count or 0),
                "tracked_item_exchange": bool(tracked_item_exchange),
                "exchange_mode": exchange_mode,
                "tracked_item_source_payload": tracked_item_source_payload,
                "tracked_items": json.dumps(tracked_items or {}, ensure_ascii=False),
            }
        )

    def write_verbose_csv(self):
        if not self.verbose_csv_path:
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
            "payload_instance_id",
            "payload_slot",
            "onboard_payloads",
            "onboard_slots",
            "multi_stop_task_ids",
            "multi_stop_pickup_count",
            "multi_stop_dropoff_count",
            "weight_kg",
            "from_location",
            "to_location",
            "lift_id",
            "duration_sec",
            "wait_time_sec",
            "distance_m",
            "energy_kwh",
            "task_duration_sec",
            "details",
            "task_source",
            "department_id",
            "waste_stream",
            "waste_volume_m3",
            "container_type",
            "pending_reason",
            "tracked_item_exchange",
            "exchange_mode",
            "tracked_item_source_payload",
            "tracked_items",
        ]

        with open(self.verbose_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.verbose_rows)

    def _estimate_total_sim_time(self) -> float:
        times = [0.0]

        for _, _, _, task in self.pending_tasks:
            times.append(task.release_time)

        for event in self.events:
            times.append(event.time)

        if self.completed_task_records:
            finish_times = [
                parse_datetime(x["finish_datetime"])
                for x in self.completed_task_records
            ]
            times.append(
                max(
                    (dt - self.clock.start_datetime).total_seconds()
                    for dt in finish_times
                )
            )

        if getattr(self, "task_generation_manager", None) and getattr(
            self.task_generation_manager, "generators", []
        ):
            times.append(getattr(self, "task_generation_horizon_sec", 0.0))

        return max(times)

    def _print_progress(self):
        now_wall = time.time()

        if now_wall - self.last_progress_update < self.progress_update_interval:
            return

        self.last_progress_update = now_wall

        elapsed = now_wall - self.wall_start_time

        total_sim = max(self.estimated_total_sim_time, self.current_time, 1e-9)
        progress = min(1.0, self.current_time / max(total_sim, 1e-9))

        bar_length = 40
        filled = int(bar_length * progress)
        bar = "#" * filled + "-" * (bar_length - filled)

        if progress > 0:
            eta = elapsed * (1 - progress) / progress
        else:
            eta = 0

        line = (
            f"\r[{bar}] "
            f"{progress*100:6.2f}% | "
            f"Sim: {self.clock.format_sim_time(self.current_time)} | "
            f"Elapsed: {elapsed:6.1f}s | "
            f"Events: {len(self.events)} | "
            f"ETA: {eta:6.1f}s | "
        )
        print(line, end="", flush=True)

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
            "lifts": [
                {
                    "lift_id": lift.id,
                    "current_floor": lift.current_floor,
                    "available_time": round(lift.available_time, 3),
                    "health_percent": round(lift.health_percent, 3),
                    "journeys_completed": lift.journeys_completed,
                    "mean_time_between_failures_hours": lift.mean_time_between_failures_hours,
                    "mean_time_to_repair_hours": lift.mean_time_to_repair_hours,
                    "failures_count": lift.failures_count,
                    "failed_until": (
                        self.clock.format_sim_time(lift.failed_until)
                        if lift.failed_until
                        else ""
                    ),
                }
                for lift in self.lifts
            ],
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

    def short_summary(self) -> dict:
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
            "sim_datetime": self.clock.format_sim_time(self.current_time),
            "duration_hms": format_duration(makespan),
            "completed_tasks": len(self.completed_task_records),
            "pending_tasks": len(self.pending_tasks),
            "failed_tasks": self.failed_tasks,
        }

    def print_summary(self):
        data = self.summary()
        print("\n=== Simulation Summary ===")
        print(json.dumps(data, indent=2))

    def print_short_summary(self):
        data = self.short_summary()
        print("\n=== Short Simulation Summary ===")
        print(json.dumps(data, indent=2))

    def print_completed_tasks(self):
        print("\n=== Completed Tasks ===")
        print(json.dumps(self.completed_task_records, indent=2))

    def _print_progress_complete(self):
        if self.wall_start_time is None:
            return

        elapsed = time.time() - self.wall_start_time
        bar_length = 40
        bar = "#" * bar_length

        print(
            f"\r[{bar}] "
            f"{100.00:6.2f}% | "
            f"Sim: {self.clock.format_sim_time(self.current_time)} | "
            f"Elapsed: {elapsed:6.1f}s | "
            f"Events: {0}",
            f"ETA: {0.0:6.1f}s | ",
            end="",
            flush=True,
        )

    def _next_pending_task_release_for_amr(self, amr: AMR) -> Optional[float]:
        feasible_release_times = []

        for _, _, _, task in self.pending_tasks:
            if task.pickup not in self.locations or task.dropoff not in self.locations:
                continue
            payload = self._payload_for_task(task)
            if payload is None:
                continue
            if not self._amr_can_carry_payload(amr, payload):
                continue

            feasible_release_times.append(task.release_time)

        if not feasible_release_times:
            return None

        return min(feasible_release_times)

    def _amr_has_return_task_pending(self, amr: AMR) -> bool:
        for _, _, _, task in self.pending_tasks:
            if (
                getattr(task, "is_idle_return", False)
                and getattr(task, "amr_id", "") == amr.id
            ):
                return True
        return False

    def _create_idle_return_task(self, amr: AMR, now: float) -> Optional[Task]:
        if amr.location_name == self.amr_centre_name:
            return None

        if self.amr_centre_name not in self.locations:
            return None

        self.synthetic_task_counter += 1

        task = Task(
            id=f"RETURN-{amr.id}-{self.synthetic_task_counter}",
            pickup=amr.location_name,
            dropoff=self.amr_centre_name,
            payload=EMPTY_PAYLOAD_NAME,
            release_time=now,
            priority=999999,
            target_time=0.0,
            labels=[],
            route_profile=None,
        )
        task.created_during_runtime = True
        task.is_idle_return = True
        task.amr_id = amr.id
        return task

    def _queue_idle_return_tasks(self, now: float):
        if not self.enable_idle_return:
            return

        for amr in self.amrs:
            if getattr(amr, "is_charging", False):
                continue
            if amr.available_time > now:
                continue
            if self._needs_post_task_recharge(amr):
                continue
            if self._amr_has_return_task_pending(amr):
                continue

            next_release = self._next_pending_task_release_for_amr(amr)

            should_return = False

            if next_release is None:
                should_return = True
            elif next_release - now > self.idle_return_window_sec:
                should_return = True

            if not should_return:
                continue

            return_task = self._create_idle_return_task(amr, now)
            if return_task is not None:
                self._queue_pending_task(return_task)


class RuntimeInputThread(threading.Thread):
    def __init__(self, sim: Simulation):
        super().__init__(daemon=True)
        self.sim = sim

    def _update_task_generators_until(self, now: float):
        if not getattr(self.sim, "task_generation_manager", None):
            return

        for record in self.sim.task_generation_manager.update_until(now):
            task = record.task
            self.sim.schedule_task_release(task)

            pickup = self.sim.locations.get(record.pickup_location)
            dropoff = self.sim.locations.get(record.dropoff_location)

            self.sim.log_step(
                event_time=task.release_time,
                event_type=record.event_type,
                task_id=task.id,
                details=record.details,
                from_location=record.pickup_location,
                to_location=record.dropoff_location,
                payload_name=self.sim._payload_log_name(record.payload_name),
                payload_instance_id=getattr(task, "payload_instance_id", ""),
                duration_sec=0.0,
                wait_time_sec=0.0,
                distance_m=0.0,
                start_time=task.release_time,
                end_time=task.release_time,
                start_node=record.pickup_location,
                end_node=record.dropoff_location,
                start_x=getattr(pickup, "x", None),
                start_y=getattr(pickup, "y", None),
                start_floor=getattr(pickup, "floor", None),
                end_x=getattr(dropoff, "x", None),
                end_y=getattr(dropoff, "y", None),
                end_floor=getattr(dropoff, "floor", None),
                status="generated",
                energy_kwh=0.0,
                task_source=record.task_source,
                department_id=record.department_id,
                waste_stream=record.waste_stream,
                waste_volume_m3=record.waste_volume_m3,
                container_type=record.container_type,
                **self.sim._task_tracking_log_kwargs(task),
            )

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

            if line.lower() == "short":
                self.sim.print_short_summary()
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
        "charge_locations": ["Stores"],
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
        {
            "name": "food_trolley",
            "weight_kg": 120,
            "length_m": 1.0,
            "width_m": 0.7,
            "height_m": 1.2,
        },
        {
            "name": "drugs_box",
            "weight_kg": 15,
            "length_m": 0.4,
            "width_m": 0.3,
            "height_m": 0.3,
        },
        {
            "name": "linen_cart",
            "weight_kg": 80,
            "length_m": 0.9,
            "width_m": 0.6,
            "height_m": 1.1,
        },
    ],
    "amrs": [
        {
            "id": "AMR-A",
            "quantity": 2,
            "payload_capacity_kg": 150,
            "payload_length_capacity_m": 1.2,
            "payload_width_capacity_m": 0.8,
            "payload_height_capacity_m": 1.3,
            "length_m": 0.8,
            "width_m": 0.6,
            "height_m": 1.2,
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
            "capacity_length_m": 1.5,
            "capacity_width_m": 1.2,
            "capacity_height_m": 2.1,
            "health_percent": 100.0,
            "health_loss_per_journey_percent": 0.05,
            "mean_time_between_failures_hours": 720.0,
            "mean_time_to_repair_hours": 4.0,
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
            "capacity_length_m": 1.5,
            "capacity_width_m": 1.2,
            "capacity_height_m": 2.1,
            "health_percent": 100.0,
            "health_loss_per_journey_percent": 0.05,
            "mean_time_between_failures_hours": 720.0,
            "mean_time_to_repair_hours": 4.0,
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

    # print(json.dumps(sim.summary(), indent=2))
    sim.write_verbose_csv()
    if args.verbose:
        print(f"Verbose CSV written to {args.verbose_csv}")


if __name__ == "__main__":
    main()
