"""
Automatic task generation for the AMR simulator.

This module keeps generated task logic outside ``simulator.py``.  The current
implementation preserves the existing department waste behaviour and JSON schema,
while providing a registry that can be extended with catering, linen, pharmacy,
parcel and other generators later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from amr_sim_models import Location, PayloadType, Task
from amr_sim_time_utils import SimulationClock


DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class GeneratedTaskRecord:
    """A generated task plus logging metadata for the simulator."""

    task: Task
    event_type: str
    details: str
    pickup_location: str
    dropoff_location: str
    payload_name: str
    task_source: str = ""
    department_id: str = ""
    waste_stream: str = ""
    waste_volume_m3: float = 0.0
    container_type: str = ""


class BaseTaskGenerator:
    """Base class for runtime task generators."""

    generator_type = "base"

    def update_until(self, now: float) -> List[GeneratedTaskRecord]:
        return []


class DepartmentWasteTaskGenerator(BaseTaskGenerator):
    """
    Runtime department waste generator.

    Existing fields are intentionally supported:
    - departments[].enabled
    - departments[].days_active
    - departments[].hours_operated_per_day
    - departments[].bed_count
    - departments[].patient_turnover
    - departments[].staff_count
    - departments[].waste.alpha/beta/gamma
    - departments[].waste.pickup_location/dropoff_location
    - departments[].waste_streams[]
    - waste_streams[].payload/container_capacity_m3/full_threshold_fraction
    """

    generator_type = "department_waste"

    def __init__(
        self,
        departments: Iterable[dict],
        waste_streams: Dict[str, dict],
        locations: Dict[str, Location],
        payloads: Dict[str, PayloadType],
        clock: SimulationClock,
        default_priority: int = 60,
    ):
        self.departments = list(departments or [])
        self.waste_streams = waste_streams or {}
        self.locations = locations or {}
        self.payloads = payloads or {}
        self.clock = clock
        self.default_priority = int(default_priority)
        self.runtime: Dict[str, Dict[str, dict]] = {}
        self.task_counter = 0
        self._init_runtime()

    def _init_runtime(self) -> None:
        self.runtime = {}

        for dept in self.departments:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                continue

            stream_names = [
                str(x).strip()
                for x in dept.get("waste_streams", [])
                if str(x).strip() in self.waste_streams
            ]
            if not stream_names:
                continue

            self.runtime[dept_id] = {}
            for stream_name in stream_names:
                stream_cfg = dict(self.waste_streams.get(stream_name, {}))
                self.runtime[dept_id][stream_name] = {
                    "last_update_time": 0.0,
                    "fill_m3": 0.0,
                    "generated_m3_total": 0.0,
                    "tasks_created": 0,
                    "container_capacity_m3": float(
                        stream_cfg.get("container_capacity_m3", 0.0) or 0.0
                    ),
                    "full_threshold_fraction": float(
                        stream_cfg.get("full_threshold_fraction", 0.8) or 0.8
                    ),
                }

    def _day_key_for_sim_time(self, sim_time_sec: float) -> str:
        dt = self.clock.sim_seconds_to_datetime(sim_time_sec)
        return DAY_KEYS[dt.weekday()]

    def _department_is_active(self, dept: dict, sim_time_sec: float) -> bool:
        if not bool(dept.get("enabled", True)):
            return False

        active_days = dept.get("days_active", [])
        if active_days:
            active = {str(x).strip().lower() for x in active_days if str(x).strip()}
            if self._day_key_for_sim_time(sim_time_sec) not in active:
                return False

        hours_operated = float(dept.get("hours_operated_per_day", 24.0) or 0.0)
        if hours_operated <= 0:
            return False

        dt = self.clock.sim_seconds_to_datetime(sim_time_sec)
        hour_decimal = dt.hour + (dt.minute / 60.0) + (dt.second / 3600.0)
        return hour_decimal < hours_operated

    def _department_hourly_waste_rate_m3(self, dept: dict) -> float:
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

        turnover_per_hour = patient_turnover / hours_operated
        return (alpha * bed_count) + (beta * turnover_per_hour) + (gamma * staff_count)

    def _make_task_id(self, dept_id: str, stream_name: str) -> str:
        self.task_counter += 1
        safe_stream = "".join(
            c if c.isalnum() else "_" for c in str(stream_name).upper()
        ).strip("_")
        return f"WASTE_{dept_id}_{safe_stream}_{self.task_counter:05d}"

    def _create_task_record(
        self,
        dept: dict,
        stream_name: str,
        release_time: float,
        waste_volume_m3: float,
    ) -> Optional[GeneratedTaskRecord]:
        dept_id = str(dept.get("id", "")).strip()
        dept_name = str(dept.get("name", dept_id)).strip()
        stream_cfg = dict(self.waste_streams.get(stream_name, {}))
        waste_cfg = dict(dept.get("waste", {}) or {})

        pickup_location = str(waste_cfg.get("pickup_location", "")).strip()
        dropoff_location = str(waste_cfg.get("dropoff_location", "")).strip()
        payload_name = str(stream_cfg.get("payload", "")).strip()

        if not pickup_location or pickup_location not in self.locations:
            return None
        if not dropoff_location or dropoff_location not in self.locations:
            return None
        if not payload_name or payload_name not in self.payloads:
            return None

        task = Task(
            id=self._make_task_id(dept_id, stream_name),
            pickup=pickup_location,
            dropoff=dropoff_location,
            payload=payload_name,
            release_time=release_time,
            target_time=0.0,
            quantity=1,
            priority=int(waste_cfg.get("priority", self.default_priority) or self.default_priority),
            created_during_runtime=True,
            labels=["waste", stream_name],
            route_profile=waste_cfg.get("route_profile") or None,
            task_source="department_waste",
            department_id=dept_id,
            waste_stream=stream_name,
            waste_volume_m3=float(waste_volume_m3),
            container_type=payload_name,
        )

        return GeneratedTaskRecord(
            task=task,
            event_type="waste_task_generated",
            details=f"Generated waste collection for {dept_name} / {stream_name}",
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            payload_name=payload_name,
            task_source="department_waste",
            department_id=dept_id,
            waste_stream=stream_name,
            waste_volume_m3=float(waste_volume_m3),
            container_type=payload_name,
        )

    def update_until(self, now: float) -> List[GeneratedTaskRecord]:
        if now <= 0 or not self.departments:
            return []

        generated: List[GeneratedTaskRecord] = []

        for dept in self.departments:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                continue

            runtime_by_stream = self.runtime.get(dept_id, {})
            if not runtime_by_stream:
                continue

            for stream_name, runtime in runtime_by_stream.items():
                last_time = float(runtime.get("last_update_time", 0.0) or 0.0)
                if now <= last_time:
                    continue

                if self._department_is_active(dept, now):
                    elapsed_hours = (now - last_time) / 3600.0
                    generated_m3 = max(
                        0.0, elapsed_hours * self._department_hourly_waste_rate_m3(dept)
                    )
                    runtime["fill_m3"] += generated_m3
                    runtime["generated_m3_total"] += generated_m3

                    trigger_volume_m3 = float(
                        runtime.get("container_capacity_m3", 0.0) or 0.0
                    ) * float(runtime.get("full_threshold_fraction", 0.8) or 0.8)

                    if trigger_volume_m3 > 0:
                        while runtime["fill_m3"] >= trigger_volume_m3:
                            record = self._create_task_record(
                                dept=dept,
                                stream_name=stream_name,
                                release_time=now,
                                waste_volume_m3=trigger_volume_m3,
                            )
                            if record is not None:
                                generated.append(record)
                            runtime["fill_m3"] -= trigger_volume_m3
                            runtime["tasks_created"] += 1

                runtime["last_update_time"] = now

        return generated


class TaskGenerationManager:
    """Registry and coordinator for all runtime task generators."""

    def __init__(
        self,
        config: dict,
        clock: SimulationClock,
        locations: Dict[str, Location],
        payloads: Dict[str, PayloadType],
    ):
        self.config = config or {}
        self.clock = clock
        self.locations = locations
        self.payloads = payloads
        self.generators: List[BaseTaskGenerator] = []
        self._build_generators()

    def _generation_enabled(self, name: str, default: bool = True) -> bool:
        # Backwards compatible: if task_generation is missing, department waste
        # still runs exactly as it did previously when waste streams/departments exist.
        cfg = self.config.get("task_generation", {}) or {}
        if cfg and not bool(cfg.get("enabled", True)):
            return False
        specific = cfg.get(name, {}) or {}
        return bool(specific.get("enabled", default))

    def _build_generators(self) -> None:
        waste_streams = {
            str(item.get("name", "")).strip(): dict(item)
            for item in self.config.get("waste_streams", [])
            if str(item.get("name", "")).strip()
        }
        departments = list(self.config.get("departments", []))

        if waste_streams and departments and self._generation_enabled("department_waste", True):
            priority = int(
                ((self.config.get("task_generation", {}) or {})
                 .get("department_waste", {}) or {})
                .get("priority", 60)
                or 60
            )
            self.generators.append(
                DepartmentWasteTaskGenerator(
                    departments=departments,
                    waste_streams=waste_streams,
                    locations=self.locations,
                    payloads=self.payloads,
                    clock=self.clock,
                    default_priority=priority,
                )
            )

    def update_until(self, now: float) -> List[GeneratedTaskRecord]:
        generated: List[GeneratedTaskRecord] = []
        for generator in self.generators:
            generated.extend(generator.update_until(now))
        return generated
