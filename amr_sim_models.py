from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


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
    length_m: float = 1.0
    width_m: float = 1.0
    height_m: float = 1.0
    # Legacy compatibility only. New editor files use length/width/height.
    size_units: float = 1.0
    # Payload-in-payload / consumables tracking.
    track_items: bool = False
    items: Dict[str, dict] = field(default_factory=dict)

    @property
    def footprint_area_m2(self) -> float:
        return max(0.0, self.length_m) * max(0.0, self.width_m)


@dataclass
class Task:
    id: str
    pickup: str
    dropoff: str
    payload: str
    release_time: float = 0.0
    target_time: float = 0.0
    quantity: int = 1
    priority: int = 100
    created_during_runtime: bool = False
    labels: List[str] = field(default_factory=list)
    route_profile: Optional[str] = None
    allowed_lifts: List[str] = field(default_factory=list)
    allowed_nodes: List[str] = field(default_factory=list)
    allowed_edges: List[Tuple[str, str]] = field(default_factory=list)

    # Runtime / waste metadata
    task_source: str = ""
    department_id: str = ""
    waste_stream: str = ""
    waste_volume_m3: float = 0.0
    container_type: str = ""
    pending_reason: str = ""
    assigned_inventory_space: str = ""
    payload_instance_id: str = ""
    is_return_task: bool = False

    # Tracked item exchange metadata. These fields are populated by automatic
    # task generation when a payload has track_items enabled. They are kept on
    # the Task object so verbose logging, completed task reporting and future
    # stock-state logic can use them without changing the core routing code.
    tracked_item_exchange: bool = False
    exchange_mode: str = ""
    tracked_item_source_payload: str = ""
    tracked_items: Dict[str, dict] = field(default_factory=dict)
    generated_volume_m3: float = 0.0

    # Optional delayed return/exchange task generated when this task completes.
    return_enabled: bool = False
    return_payload: str = ""
    return_delay_minutes: float = 0.0
    return_route_profile: str = ""
    return_priority: int = 0
    requires_staff: bool = False
    staff_initial_count: int = 1
    staff_resource_name: str = ""
    staff_category_key: str = ""


@dataclass
class Lift:
    id: str
    served_floors: List[int]
    speed_floors_per_sec: float
    door_time_sec: float
    boarding_time_sec: float
    speed_m_per_sec: float = 0.0
    floor_locations: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    capacity_length_m: float = 1.0
    capacity_width_m: float = 1.0
    capacity_height_m: float = 2.0
    # Legacy compatibility only.
    capacity_size_units: float = 1.0
    current_floor: int = 0
    available_time: float = 0.0
    car_mass_kg: float = 1200.0
    counterweight_ratio: float = 0.5
    travel_efficiency: float = 0.75
    door_power_w: float = 800.0
    standby_power_w: float = 120.0
    regen_efficiency: float = 0.2
    health_percent: float = 100.0
    health_loss_per_journey_percent: float = 0.05
    mean_time_between_failures_hours: float = 720.0
    mean_time_to_repair_hours: float = 4.0
    failed_until: float = 0.0
    journeys_completed: int = 0
    operating_time_since_failure_sec: float = 0.0
    failures_count: int = 0

    def can_serve(self, floor_a: int, floor_b: int) -> bool:
        return floor_a in self.served_floors and floor_b in self.served_floors

    def travel_speed_m_per_sec(self, floor_height_m: float) -> float:
        if self.speed_m_per_sec > 0:
            return float(self.speed_m_per_sec)
        return max(0.0, float(self.speed_floors_per_sec or 0.0)) * float(floor_height_m)

    def vertical_travel_duration_sec(self, floor_delta: int, floor_height_m: float) -> float:
        travel_m = abs(int(floor_delta)) * float(floor_height_m)
        return travel_m / max(self.travel_speed_m_per_sec(floor_height_m), 1e-9)

    def can_fit(self, payload: PayloadType, amr: Optional["AMR"] = None) -> bool:
        total_length = max(payload.length_m, amr.length_m if amr else 0.0)
        total_width = max(payload.width_m, amr.width_m if amr else 0.0)
        total_height = max(payload.height_m, amr.height_m if amr else 0.0)
        return (
            total_length <= self.capacity_length_m
            and total_width <= self.capacity_width_m
            and total_height <= self.capacity_height_m
        )

    def apply_journey_wear(self) -> None:
        loss = max(0.0, float(self.health_loss_per_journey_percent or 0.0))
        self.health_percent = max(0.0, round(float(self.health_percent) - loss, 3))
        self.journeys_completed += 1

    def location_on_floor(self, floor: int) -> Location:
        if floor not in self.floor_locations:
            raise ValueError(
                f"Lift {self.id} has no x,y location defined on floor {floor}"
            )
        x, y = self.floor_locations[floor]
        return Location(name=f"{self.id}-F{floor}", floor=floor, x=x, y=y)


@dataclass
class AMR:
    id: str
    payload_capacity_kg: float
    payload_length_capacity_m: float = 1.0
    payload_width_capacity_m: float = 1.0
    payload_height_capacity_m: float = 1.0
    length_m: float = 0.8
    width_m: float = 0.6
    height_m: float = 1.2
    speed_m_per_sec: float = 1.0
    motor_power_w: float = 750.0
    battery_capacity_kwh: float = 5.0
    battery_charge_rate_kw: float = 1.5
    recharge_threshold_percent: float = 20.0
    battery_soc_percent: float = 100.0
    # Legacy compatibility only.
    payload_size_capacity: float = 1.0
    available_time: float = 0.0
    location_name: str = ""
    completed_tasks: int = 0
    total_busy_time: float = 0.0
    total_charge_time: float = 0.0
    total_energy_used_kwh: float = 0.0
    is_charging: bool = False
    payload: str = ""
    payload_instance_id: str = ""

    def can_carry(self, payload: PayloadType) -> bool:
        return (
            payload.weight_kg <= self.payload_capacity_kg
            and payload.length_m <= self.payload_length_capacity_m
            and payload.width_m <= self.payload_width_capacity_m
            and payload.height_m <= self.payload_height_capacity_m
        )

    def battery_energy_kwh(self) -> float:
        return self.battery_capacity_kwh * (self.battery_soc_percent / 100.0)

    def min_reserve_energy_kwh(self) -> float:
        return self.battery_capacity_kwh * (self.recharge_threshold_percent / 100.0)

    def consume_energy(self, energy_kwh: float):
        remaining = max(0.0, self.battery_energy_kwh() - energy_kwh)
        self.battery_soc_percent = (
            100.0 * remaining / max(self.battery_capacity_kwh, 1e-9)
        )
        self.total_energy_used_kwh += energy_kwh

    def charge_duration_sec_to_full(self) -> float:
        missing_kwh = max(0.0, self.battery_capacity_kwh - self.battery_energy_kwh())
        return (missing_kwh / max(self.battery_charge_rate_kw, 1e-9)) * 3600.0

    def charge_to_full(self):
        self.battery_soc_percent = 100.0
