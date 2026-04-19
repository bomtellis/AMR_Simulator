from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


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
    target_time: float = 0.0
    quantity: int = 1
    priority: int = 100
    created_during_runtime: bool = False
    labels: List[str] = field(default_factory=list)
    route_profile: Optional[str] = None
    allowed_lifts: List[str] = field(default_factory=list)
    allowed_nodes: List[str] = field(default_factory=list)
    allowed_edges: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class Lift:
    id: str
    served_floors: List[int]
    speed_floors_per_sec: float
    door_time_sec: float
    boarding_time_sec: float
    floor_locations: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    capacity_size_units: float = 1.0
    current_floor: int = 0
    available_time: float = 0.0
    car_mass_kg: float = 1200.0
    counterweight_ratio: float = 0.5
    travel_efficiency: float = 0.75
    door_power_w: float = 800.0
    standby_power_w: float = 120.0
    regen_efficiency: float = 0.2

    def can_serve(self, floor_a: int, floor_b: int) -> bool:
        return floor_a in self.served_floors and floor_b in self.served_floors

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
    payload_size_capacity: float
    speed_m_per_sec: float
    motor_power_w: float
    battery_capacity_kwh: float
    battery_charge_rate_kw: float
    recharge_threshold_percent: float = 20.0
    battery_soc_percent: float = 100.0
    available_time: float = 0.0
    location_name: str = ""
    completed_tasks: int = 0
    total_busy_time: float = 0.0
    total_charge_time: float = 0.0
    total_energy_used_kwh: float = 0.0
    is_charging: bool = False

    def can_carry(self, payload: PayloadType) -> bool:
        return (
            payload.weight_kg <= self.payload_capacity_kg
            and payload.size_units <= self.payload_size_capacity
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
