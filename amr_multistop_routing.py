"""
Multi-stop batching helpers for AMR simulator.

This module is intentionally independent of the PySide editor so simulator.py can
import it without a GUI dependency.  It groups compatible released tasks into one
AMR tour when the AMR has multiple payload slots and multi_stop_enabled is true.

Expected task fields:
    id, pickup, dropoff, payload, priority, release_datetime, route_profile

Expected payload fields:
    name, weight_kg, length_m, width_m, height_m

Expected AMR fields:
    id, multi_stop_enabled, payload_slots
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import permutations
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


TravelCostFn = Callable[[str, str, Optional[str]], float]


@dataclass(frozen=True)
class PayloadSpec:
    name: str
    weight_kg: float = 0.0
    length_m: float = 0.0
    width_m: float = 0.0
    height_m: float = 0.0

    @classmethod
    def from_dict(cls, value: dict) -> "PayloadSpec":
        return cls(
            name=str(value.get("name", "")).strip(),
            weight_kg=float(value.get("weight_kg", 0.0) or 0.0),
            length_m=float(value.get("length_m", 0.0) or 0.0),
            width_m=float(value.get("width_m", 0.0) or 0.0),
            height_m=float(value.get("height_m", 0.0) or 0.0),
        )


@dataclass(frozen=True)
class PayloadSlot:
    name: str
    payload_capacity_kg: float
    payload_length_capacity_m: float
    payload_width_capacity_m: float
    payload_height_capacity_m: float

    @classmethod
    def from_dict(cls, value: dict, index: int) -> "PayloadSlot":
        return cls(
            name=str(value.get("name", "")).strip() or f"Slot {index}",
            payload_capacity_kg=float(value.get("payload_capacity_kg", 0.0) or 0.0),
            payload_length_capacity_m=float(value.get("payload_length_capacity_m", 0.0) or 0.0),
            payload_width_capacity_m=float(value.get("payload_width_capacity_m", 0.0) or 0.0),
            payload_height_capacity_m=float(value.get("payload_height_capacity_m", 0.0) or 0.0),
        )

    def can_hold(self, payload: PayloadSpec) -> bool:
        return (
            payload.weight_kg <= self.payload_capacity_kg
            and payload.length_m <= self.payload_length_capacity_m
            and payload.width_m <= self.payload_width_capacity_m
            and payload.height_m <= self.payload_height_capacity_m
        )


@dataclass
class MultiStopLeg:
    action: str
    location: str
    task_id: str
    payload: str
    slot_name: str


@dataclass
class MultiStopPlan:
    amr_id: str
    tasks: List[dict]
    slot_assignments: Dict[str, str]
    ordered_legs: List[MultiStopLeg]
    estimated_travel_cost: float
    route_profile: str = ""
    metadata: dict = field(default_factory=dict)

    def as_task_sequence(self) -> List[dict]:
        """Return simulator-friendly leg dictionaries."""
        return [
            {
                "action": leg.action,
                "location": leg.location,
                "task_id": leg.task_id,
                "payload": leg.payload,
                "slot_name": leg.slot_name,
            }
            for leg in self.ordered_legs
        ]


def normalise_payload_slots(amr: dict) -> List[PayloadSlot]:
    raw_slots = amr.get("payload_slots") if isinstance(amr, dict) else None
    slots: List[PayloadSlot] = []
    if isinstance(raw_slots, list):
        for index, raw in enumerate(raw_slots, start=1):
            if isinstance(raw, dict):
                slots.append(PayloadSlot.from_dict(raw, index))

    if not slots:
        slots.append(
            PayloadSlot(
                name="Slot 1",
                payload_capacity_kg=float(amr.get("payload_capacity_kg", 100) or 100),
                payload_length_capacity_m=float(amr.get("payload_length_capacity_m", 1.0) or 1.0),
                payload_width_capacity_m=float(amr.get("payload_width_capacity_m", 1.0) or 1.0),
                payload_height_capacity_m=float(amr.get("payload_height_capacity_m", 1.0) or 1.0),
            )
        )
    return slots


def is_multi_stop_amr(amr: dict) -> bool:
    slots = normalise_payload_slots(amr)
    return bool(amr.get("multi_stop_enabled", len(slots) > 1)) and len(slots) > 1


def _task_datetime(task: dict) -> datetime:
    value = str(task.get("release_datetime", "")).strip()
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.min


def _task_priority_key(task: dict) -> tuple:
    return (
        -int(float(task.get("priority", 0) or 0)),
        _task_datetime(task),
        str(task.get("id", "")),
    )


def _payload_for_task(task: dict, payloads_by_name: Dict[str, PayloadSpec]) -> Optional[PayloadSpec]:
    return payloads_by_name.get(str(task.get("payload", "")).strip())


def assign_tasks_to_slots(
    amr: dict,
    candidate_tasks: Sequence[dict],
    payloads_by_name: Dict[str, PayloadSpec],
) -> Optional[Dict[str, str]]:
    """Assign each task to one AMR payload slot, or return None if impossible."""
    slots = normalise_payload_slots(amr)
    used_slots = set()
    assignments: Dict[str, str] = {}

    # Largest/heaviest payloads first avoids small tasks consuming the only large slot.
    sortable = []
    for task in candidate_tasks:
        payload = _payload_for_task(task, payloads_by_name)
        if payload is None:
            return None
        sortable.append((payload.weight_kg, payload.length_m * payload.width_m * payload.height_m, str(task.get("id", "")), task, payload))

    for _weight, _volume, _task_id, task, payload in sorted(sortable, reverse=True):
        assigned = None
        for slot in slots:
            if slot.name in used_slots:
                continue
            if slot.can_hold(payload):
                assigned = slot.name
                break
        if assigned is None:
            return None
        task_id = str(task.get("id", ""))
        assignments[task_id] = assigned
        used_slots.add(assigned)

    return assignments


def select_candidate_tasks(
    amr: dict,
    pending_tasks: Sequence[dict],
    payloads_by_name: Dict[str, PayloadSpec],
    max_tasks: Optional[int] = None,
) -> List[dict]:
    """Return the highest-priority compatible batch for the AMR."""
    slots = normalise_payload_slots(amr)
    limit = min(max_tasks or len(slots), len(slots))
    if limit <= 0:
        return []

    selected: List[dict] = []
    for task in sorted(pending_tasks, key=_task_priority_key):
        trial = selected + [task]
        if len(trial) > limit:
            continue
        if assign_tasks_to_slots(amr, trial, payloads_by_name) is not None:
            selected.append(task)
        if len(selected) >= limit:
            break

    return selected


def _route_cost(
    start_location: str,
    pickup_order: Sequence[dict],
    dropoff_order: Sequence[dict],
    travel_cost: TravelCostFn,
    route_profile: Optional[str],
) -> Tuple[float, List[Tuple[str, dict]]]:
    current = start_location
    total = 0.0
    route: List[Tuple[str, dict]] = []

    for task in pickup_order:
        pickup = str(task.get("pickup", ""))
        total += float(travel_cost(current, pickup, route_profile))
        current = pickup
        route.append(("pickup", task))

    for task in dropoff_order:
        dropoff = str(task.get("dropoff", ""))
        total += float(travel_cost(current, dropoff, route_profile))
        current = dropoff
        route.append(("dropoff", task))

    return total, route


def optimise_pickup_then_dropoff_order(
    start_location: str,
    tasks: Sequence[dict],
    travel_cost: TravelCostFn,
    route_profile: Optional[str] = None,
    exhaustive_limit: int = 6,
) -> Tuple[float, List[Tuple[str, dict]]]:
    """
    Find a route that picks up all payloads before delivery.

    This keeps simulator state simple: the AMR only delivers payloads after every
    assigned slot has been loaded.  For larger batches it uses a nearest-neighbour
    approximation to avoid factorial blow-up.
    """
    tasks = list(tasks)
    if not tasks:
        return 0.0, []

    if len(tasks) <= exhaustive_limit:
        best: Optional[Tuple[float, List[Tuple[str, dict]]]] = None
        for pickup_order in permutations(tasks):
            for dropoff_order in permutations(tasks):
                cost, route = _route_cost(start_location, pickup_order, dropoff_order, travel_cost, route_profile)
                if best is None or cost < best[0]:
                    best = (cost, route)
        return best if best is not None else (0.0, [])

    remaining_pickups = list(tasks)
    pickup_order: List[dict] = []
    current = start_location
    while remaining_pickups:
        next_task = min(
            remaining_pickups,
            key=lambda task: float(travel_cost(current, str(task.get("pickup", "")), route_profile)),
        )
        pickup_order.append(next_task)
        remaining_pickups.remove(next_task)
        current = str(next_task.get("pickup", ""))

    remaining_dropoffs = list(tasks)
    dropoff_order: List[dict] = []
    while remaining_dropoffs:
        next_task = min(
            remaining_dropoffs,
            key=lambda task: float(travel_cost(current, str(task.get("dropoff", "")), route_profile)),
        )
        dropoff_order.append(next_task)
        remaining_dropoffs.remove(next_task)
        current = str(next_task.get("dropoff", ""))

    return _route_cost(start_location, pickup_order, dropoff_order, travel_cost, route_profile)


def build_multi_stop_plan(
    amr: dict,
    pending_tasks: Sequence[dict],
    payloads: Iterable[dict],
    start_location: Optional[str],
    travel_cost: TravelCostFn,
    max_tasks: Optional[int] = None,
) -> Optional[MultiStopPlan]:
    """
    Build a multi-stop plan for simulator.py.

    Return None when the AMR is not a multi-stop AMR or no compatible task batch
    can be made. The simulator should then fall back to the existing single-task
    scheduler.
    """
    if not is_multi_stop_amr(amr):
        return None

    payloads_by_name = {
        spec.name: spec for spec in (PayloadSpec.from_dict(item) for item in payloads) if spec.name
    }
    candidates = select_candidate_tasks(amr, pending_tasks, payloads_by_name, max_tasks=max_tasks)
    if len(candidates) < 2:
        return None

    assignments = assign_tasks_to_slots(amr, candidates, payloads_by_name)
    if assignments is None:
        return None

    route_profile = str(candidates[0].get("route_profile", "") or "")
    start = str(start_location or amr.get("current_location") or amr.get("start_location") or "")
    cost, route_steps = optimise_pickup_then_dropoff_order(start, candidates, travel_cost, route_profile)

    legs: List[MultiStopLeg] = []
    for action, task in route_steps:
        task_id = str(task.get("id", ""))
        legs.append(
            MultiStopLeg(
                action=action,
                location=str(task.get("pickup" if action == "pickup" else "dropoff", "")),
                task_id=task_id,
                payload=str(task.get("payload", "")),
                slot_name=assignments.get(task_id, ""),
            )
        )

    return MultiStopPlan(
        amr_id=str(amr.get("id", "")),
        tasks=list(candidates),
        slot_assignments=assignments,
        ordered_legs=legs,
        estimated_travel_cost=float(cost),
        route_profile=route_profile,
        metadata={"multi_stop_task_count": len(candidates)},
    )
