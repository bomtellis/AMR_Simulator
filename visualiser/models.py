import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LOGISTICS_TASK_GENERATION_CATEGORIES = [
    ("catering", "Catering"),
    ("pharmacy", "Pharmacy"),
    ("linen", "Linen"),
    ("waste", "Waste"),
    ("stores", "Stores"),
    ("ssd", "SSD"),
]


def normalise_amr_payload_slots(amr: dict) -> list:
    """Return payload slot definitions, migrating legacy single-capacity AMRs."""
    if not isinstance(amr, dict):
        amr = {}

    slots = amr.get("payload_slots", [])
    clean = []

    if isinstance(slots, list):
        for idx, slot in enumerate(slots, start=1):
            if not isinstance(slot, dict):
                continue
            clean_slot = {
                "name": str(slot.get("name", "")).strip() or f"Slot {idx}",
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
            clean.append(clean_slot)

    if not clean:
        clean = [
            {
                "name": "Slot 1",
                "payload_capacity_kg": float(
                    amr.get("payload_capacity_kg", 100) or 100
                ),
                "payload_length_capacity_m": float(
                    amr.get("payload_length_capacity_m", 1.0) or 1.0
                ),
                "payload_width_capacity_m": float(
                    amr.get("payload_width_capacity_m", 1.0) or 1.0
                ),
                "payload_height_capacity_m": float(
                    amr.get("payload_height_capacity_m", 1.0) or 1.0
                ),
            }
        ]

    return clean


def amr_supports_manual_tasks(amr: dict) -> bool:
    return len(normalise_amr_payload_slots(amr)) == 1


def default_task_generation_category(label: str) -> dict:
    return {
        "enabled": False,
        "display_name": label,
        "generation_mode": "scheduled",
        "priority": 100,
        "pickup_location": "",
        "dropoff_location": "",
        "dropoff_locations": [],
        "payload": "",
        "tracked_item_exchange": False,
        "exchange_mode": "top_up_only",
        "return_enabled": False,
        "return_payload": "",
        "route_profile": "",
        "days_active": ["mon", "tue", "wed", "thu", "fri"],
        "schedule_times": [],
        "frequency_per_day": 0.0,
        "volume_per_event_m3": 0.0,
        "threshold_volume_m3": 0.0,
        "base_daily_volume_m3": 0.0,
        "notes": "",
    }


def default_task_generation_config() -> dict:
    categories = {
        key: default_task_generation_category(label)
        for key, label in LOGISTICS_TASK_GENERATION_CATEGORIES
    }

    categories["catering"].update(
        {
            "generation_mode": "scheduled",
            "priority": 40,
            "schedule_times": ["07:30", "11:45", "16:45"],
            "return_enabled": True,
            "return_delay_minutes": 0,
        }
    )
    categories["pharmacy"].update(
        {
            "generation_mode": "scheduled_sporadic",
            "priority": 30,
            "schedule_times": ["10:00", "15:00"],
            "frequency_per_day": 2.0,
        }
    )
    categories["linen"].update(
        {
            "generation_mode": "threshold",
            "priority": 55,
            "threshold_volume_m3": 0.8,
            "base_daily_volume_m3": 0.0,
            "return_enabled": True,
            "return_delay_minutes": 0,
        }
    )
    categories["waste"].update(
        {
            "enabled": True,
            "generation_mode": "threshold",
            "priority": 60,
            "threshold_volume_m3": 0.24,
            "base_daily_volume_m3": 0.0,
            "return_enabled": True,
            "return_delay_minutes": 0,
        }
    )
    categories["stores"].update(
        {
            "generation_mode": "scheduled",
            "priority": 70,
            "schedule_times": ["09:30", "14:30"],
        }
    )
    categories["ssd"].update(
        {
            "generation_mode": "scheduled_threshold",
            "priority": 35,
            "schedule_times": ["08:00", "12:00", "17:00"],
            "return_enabled": True,
            "return_delay_minutes": 0,
        }
    )

    return {
        "enabled": True,
        # Backwards compatibility for the current waste generator module.
        "department_waste": {
            "enabled": True,
            "priority": 60,
        },
        "categories": categories,
    }


def merge_task_generation_defaults(value: Optional[dict]) -> dict:
    merged = default_task_generation_config()
    if not isinstance(value, dict):
        return merged

    merged["enabled"] = bool(value.get("enabled", merged["enabled"]))

    if isinstance(value.get("department_waste"), dict):
        merged["department_waste"].update(value.get("department_waste", {}))

    incoming_categories = value.get("categories", {})
    if isinstance(incoming_categories, dict):
        for key, incoming in incoming_categories.items():
            if key not in merged["categories"]:
                merged["categories"][key] = (
                    dict(incoming) if isinstance(incoming, dict) else {}
                )
            elif isinstance(incoming, dict):
                merged["categories"][key].update(incoming)

    # Support older experiments where categories were stored directly under task_generation.
    for key, _label in LOGISTICS_TASK_GENERATION_CATEGORIES:
        if isinstance(value.get(key), dict):
            merged["categories"][key].update(value[key])

    for category in merged["categories"].values():
        if not isinstance(category, dict):
            continue
        dropoff_locations = category.get("dropoff_locations")
        if isinstance(dropoff_locations, list):
            clean = [str(x).strip() for x in dropoff_locations if str(x).strip()]
        else:
            clean = []
        legacy_dropoff = str(category.get("dropoff_location", "")).strip()
        if legacy_dropoff and legacy_dropoff not in clean:
            clean.insert(0, legacy_dropoff)
        category["dropoff_locations"] = clean
        category["dropoff_location"] = clean[0] if clean else legacy_dropoff

    # Keep waste category and department_waste switch in step.
    if "waste" in merged["categories"]:
        merged["department_waste"]["enabled"] = bool(
            merged["categories"]["waste"].get(
                "enabled", merged["department_waste"].get("enabled", True)
            )
        )
        merged["department_waste"]["priority"] = int(
            float(
                merged["categories"]["waste"].get(
                    "priority", merged["department_waste"].get("priority", 60)
                )
            )
        )

    return merged


DEFAULT_JSON = {
    "simulation": {
        "start_datetime": "2026-01-05T06:00:00",
        "end_datetime": "2026-01-06T06:00:00",
        "tick_rate": 1000,
        "generated_task_release_stagger_sec": 0.25,
        "precompute_static_routes": True,
        "route_precompute_max_pairs": 100000,
        "max_multi_stop_candidate_tasks": 8,
        "max_single_candidate_tasks": 8,
        "max_assignments_per_tick": 25,
        "assignment_continue_delay_sec": 0.001,
    },
    "building": {
        "load_unload_time_sec": 20.0,
        "floor_height_m": 4.0,
        "charge_locations": ["AMR-CENTRE"],
    },
    "locations": [],
    "corridors": {
        "nodes": [],
        "edges": [],
        "auto_connect": False,
    },
    "payloads": [],
    "waste_streams": [],
    "departments": [],
    "amrs": [],
    "lifts": [],
    "floor_dxf_files": [],
    "tasks": [],
    "task_generation": default_task_generation_config(),
    "route_profiles": {
        "default": {
            "allowed_lifts": [],
            "allowed_nodes": [],
            "allowed_edges": [],
        }
    },
}


class JsonStore:
    def __init__(self, data: Optional[dict] = None):
        self.data = deepcopy(data) if data else deepcopy(DEFAULT_JSON)
        self.ensure_simulation_defaults()
        self.ensure_task_generation_defaults()
        self.ensure_payload_defaults()
        self.ensure_amr_defaults()

    def ensure_simulation_defaults(self) -> None:
        simulation = self.data.setdefault("simulation", {})
        default_simulation = DEFAULT_JSON.get("simulation", {})
        simulation.setdefault(
            "start_datetime",
            default_simulation.get("start_datetime", "2026-01-05T06:00:00"),
        )
        simulation.setdefault(
            "end_datetime",
            default_simulation.get("end_datetime", "2026-01-06T06:00:00"),
        )
        simulation.setdefault("tick_rate", default_simulation.get("tick_rate", 1000))
        simulation.setdefault(
            "generated_task_release_stagger_sec",
            default_simulation.get("generated_task_release_stagger_sec", 0.25),
        )
        simulation.setdefault(
            "precompute_static_routes",
            default_simulation.get("precompute_static_routes", True),
        )
        simulation.setdefault(
            "route_precompute_max_pairs",
            default_simulation.get("route_precompute_max_pairs", 100000),
        )
        simulation.setdefault(
            "max_multi_stop_candidate_tasks",
            default_simulation.get("max_multi_stop_candidate_tasks", 8),
        )
        simulation.setdefault(
            "max_single_candidate_tasks",
            default_simulation.get("max_single_candidate_tasks", 8),
        )
        simulation.setdefault(
            "max_assignments_per_tick",
            default_simulation.get("max_assignments_per_tick", 25),
        )
        simulation.setdefault(
            "assignment_continue_delay_sec",
            default_simulation.get("assignment_continue_delay_sec", 0.001),
        )

    def ensure_payload_defaults(self) -> None:
        for payload in self.data.setdefault("payloads", []):
            payload.setdefault("track_items", False)

            items = payload.get("items", {})

            if isinstance(items, list):
                converted = {}
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    converted[name] = item
                items = converted

            if not isinstance(items, dict):
                items = {}

            clean = {}

            for name, cfg in items.items():
                if not str(name).strip():
                    continue

                cfg = cfg if isinstance(cfg, dict) else {}

                clean[str(name).strip()] = {
                    "max": float(cfg.get("max", 100)),
                    "top_up_threshold": float(cfg.get("top_up_threshold", 15)),
                    "usage_rate": str(cfg.get("usage_rate", "scheduled_sporadic")),
                    "consumption_per_day": float(cfg.get("consumption_per_day", 0.0)),
                    "exchange_payload": str(cfg.get("exchange_payload", "")),
                    "source_location": str(cfg.get("source_location", "")),
                }

            payload["items"] = clean

    def ensure_amr_defaults(self) -> None:
        for amr in self.data.setdefault("amrs", []):
            slots = normalise_amr_payload_slots(amr)
            amr["payload_slots"] = slots

            # Keep the legacy top-level fields populated from the first slot so older
            # simulator/reporting code continues to read a sensible single-slot value.
            primary = slots[0]
            amr["payload_capacity_kg"] = float(primary.get("payload_capacity_kg", 0.0))
            amr["payload_length_capacity_m"] = float(
                primary.get("payload_length_capacity_m", 0.0)
            )
            amr["payload_width_capacity_m"] = float(
                primary.get("payload_width_capacity_m", 0.0)
            )
            amr["payload_height_capacity_m"] = float(
                primary.get("payload_height_capacity_m", 0.0)
            )
            amr["manual_task_compatible"] = len(slots) == 1
            amr["multi_stop_enabled"] = bool(
                amr.get("multi_stop_enabled", len(slots) > 1) and len(slots) > 1
            )

    def has_manual_task_compatible_amr(self) -> bool:
        self.ensure_amr_defaults()
        return any(amr_supports_manual_tasks(amr) for amr in self.data.get("amrs", []))

    def multi_stop_enabled_amrs(self) -> list:
        self.ensure_amr_defaults()
        return [
            amr
            for amr in self.data.get("amrs", [])
            if bool(amr.get("multi_stop_enabled", False))
            and len(normalise_amr_payload_slots(amr)) > 1
        ]

    def ensure_task_generation_defaults(self) -> dict:
        self.data["task_generation"] = merge_task_generation_defaults(
            self.data.get("task_generation", {})
        )
        return self.data["task_generation"]

    def task_generation(self) -> dict:
        return self.ensure_task_generation_defaults()

    def set_task_generation(self, value: dict) -> None:
        self.data["task_generation"] = merge_task_generation_defaults(value)

    @classmethod
    def from_file(cls, path: str) -> "JsonStore":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def save(self, path: str) -> None:
        self.ensure_simulation_defaults()
        self.ensure_amr_defaults()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def floor_dxf_path(self, floor: int) -> Optional[str]:
        for entry in self.data.get("floor_dxf_files", []):
            try:
                if int(entry.get("floor")) == int(floor):
                    path = (entry.get("filepath") or "").strip()
                    return path or None
            except Exception:
                continue
        return None

    def charge_locations(self) -> list:
        building = self.data.setdefault("building", {})
        locations = building.get("charge_locations")

        if isinstance(locations, list):
            return [str(x).strip() for x in locations if str(x).strip()]

        legacy = str(building.get("charge_location", "")).strip()
        return [legacy] if legacy else []

    def set_charge_locations(self, locations: list) -> None:
        self.data.setdefault("building", {})["charge_locations"] = [
            str(x).strip() for x in locations if str(x).strip()
        ]
        self.data["building"].pop("charge_location", None)

    def set_floor_dxf_path(self, floor: int, filepath: str) -> None:
        entries = self.data.setdefault("floor_dxf_files", [])
        payload = {"floor": int(floor), "filepath": str(filepath)}
        for entry in entries:
            try:
                if int(entry.get("floor")) == int(floor):
                    entry.clear()
                    entry.update(payload)
                    return
            except Exception:
                continue
        entries.append(payload)
        entries.sort(key=lambda item: int(item.get("floor", 0)))

    def clear_floor_dxf_path(self, floor: int) -> None:
        self.data["floor_dxf_files"] = [
            entry
            for entry in self.data.get("floor_dxf_files", [])
            if int(entry.get("floor", -(10**9))) != int(floor)
        ]

    def names_in_use(self) -> set:
        names = set()
        for loc in self.data.get("locations", []):
            names.add(loc["name"])
        for node in self.data.get("corridors", {}).get("nodes", []):
            names.add(node["name"])
        for dept in self.data.get("departments", []):
            name = str(dept.get("name", "")).strip()
            if name:
                names.add(name)
        for lift in self.data.get("lifts", []):
            for floor_str in lift.get("floor_locations", {}):
                names.add(f"{lift['id']}-F{floor_str}")
        return names

    def all_points(self) -> Dict[str, dict]:
        result = {}
        for item in self.data.get("locations", []):
            result[item["name"]] = {**item, "kind": "location"}
        for item in self.data.get("corridors", {}).get("nodes", []):
            result[item["name"]] = {**item, "kind": "corridor_node"}
        for lift in self.data.get("lifts", []):
            lift_id = lift["id"]
            for floor_str, pos in lift.get("floor_locations", {}).items():
                result[f"{lift_id}-F{floor_str}"] = {
                    "name": f"{lift_id}-F{floor_str}",
                    "floor": int(floor_str),
                    "x": pos["x"],
                    "y": pos["y"],
                    "kind": "lift_node",
                    "lift_id": lift_id,
                }

        for dept in self.data.get("departments", []):
            name = str(dept.get("name", "")).strip()
            if not name:
                continue
            try:
                floor = int(dept.get("floor", 0))
                x = float(dept.get("x", 0.0))
                y = float(dept.get("y", 0.0))
            except Exception:
                continue

            result[name] = {
                "name": name,
                "floor": floor,
                "x": x,
                "y": y,
                "kind": "department",
                "department_id": str(dept.get("id", "")).strip() or name,
            }

        return result

    def points_for_floor(self, floor: int) -> Dict[str, dict]:
        return {
            name: point
            for name, point in self.all_points().items()
            if int(point["floor"]) == int(floor)
        }

    def locations_for_floor(self, floor: int) -> List[dict]:
        return [
            x for x in self.data.get("locations", []) if int(x["floor"]) == int(floor)
        ]

    def corridor_nodes_for_floor(self, floor: int) -> List[dict]:
        return [
            x
            for x in self.data.get("corridors", {}).get("nodes", [])
            if int(x["floor"]) == int(floor)
        ]

    def lift_nodes_for_floor(self, floor: int) -> List[dict]:
        result = []
        for lift in self.data.get("lifts", []):
            key = str(floor)
            if key in lift.get("floor_locations", {}):
                pos = lift["floor_locations"][key]
                result.append(
                    {
                        "name": f"{lift['id']}-F{floor}",
                        "floor": floor,
                        "x": pos["x"],
                        "y": pos["y"],
                        "kind": "lift_node",
                        "lift_id": lift["id"],
                    }
                )
        return result

    def edges_for_floor(self, floor: int) -> List[dict]:
        points = self.all_points()
        edges = []
        for edge in self.data.get("corridors", {}).get("edges", []):
            a = points.get(edge["from"])
            b = points.get(edge["to"])
            if a and b and int(a["floor"]) == floor and int(b["floor"]) == floor:
                edges.append(edge)
        return edges

    def add_corridor_node(self, name: str, floor: int, x: float, y: float) -> None:
        self.data["corridors"]["nodes"].append(
            {"name": name, "floor": floor, "x": round(x, 3), "y": round(y, 3)}
        )

    def add_location(self, name: str, floor: int, x: float, y: float) -> None:
        self.data["locations"].append(
            {
                "name": name,
                "floor": floor,
                "x": round(x, 3),
                "y": round(y, 3),
                "bounding_box": [],
            }
        )

    def set_location_bounding_box(self, location_name: str, points: list) -> None:
        for item in self.data.get("locations", []):
            if item.get("name") == location_name:
                lx = float(item.get("x", 0.0))
                ly = float(item.get("y", 0.0))
                item["bounding_box"] = [
                    {
                        "dx": round(float(p["x"]) - lx, 3),
                        "dy": round(float(p["y"]) - ly, 3),
                    }
                    for p in points
                ]
                return

    def location_bounding_box_metrics(self, location_name: str) -> dict:
        points = self.get_location_bounding_box_points(location_name)
        if len(points) < 3:
            return {"length": 0.0, "width": 0.0, "area": 0.0}

        xs = [float(p["x"]) for p in points]
        ys = [float(p["y"]) for p in points]

        length = max(xs) - min(xs)
        width = max(ys) - min(ys)

        area = 0.0
        for i, p1 in enumerate(points):
            p2 = points[(i + 1) % len(points)]
            area += (float(p1["x"]) * float(p2["y"])) - (
                float(p2["x"]) * float(p1["y"])
            )
        area = abs(area) / 2.0

        return {
            "length": round(length, 3),
            "width": round(width, 3),
            "area": round(area, 3),
        }

    def remove_location_bounding_box(self, location_name: str) -> None:
        for item in self.data.get("locations", []):
            if item.get("name") == location_name:
                item.pop("bounding_box", None)
                return

    def get_location_bounding_box_points(self, location_name: str) -> list:
        for item in self.data.get("locations", []):
            if item.get("name") == location_name:
                lx = float(item.get("x", 0.0))
                ly = float(item.get("y", 0.0))

                points = []
                for p in item.get("bounding_box", []):
                    if "dx" in p and "dy" in p:
                        points.append(
                            {
                                "x": round(lx + float(p["dx"]), 3),
                                "y": round(ly + float(p["dy"]), 3),
                            }
                        )
                    else:
                        # Backwards compatibility for old absolute boxes
                        points.append(
                            {
                                "x": round(float(p["x"]), 3),
                                "y": round(float(p["y"]), 3),
                            }
                        )
                return points

        return []

    def get_location(self, location_name: str) -> Optional[dict]:
        for item in self.data.get("locations", []):
            if item.get("name") == location_name:
                return item
        return None

    def get_location_inventory_spaces(self, location_name: str) -> list:
        location = self.get_location(location_name)
        if not location:
            return []
        return deepcopy(location.get("inventory_spaces", []))

    def set_location_inventory_spaces(self, location_name: str, spaces: list) -> None:
        location = self.get_location(location_name)
        if not location:
            return

        lx = float(location.get("x", 0.0))
        ly = float(location.get("y", 0.0))

        clean_spaces = []
        for idx, space in enumerate(spaces, start=1):
            name = str(space.get("name", "")).strip() or f"Inventory {idx}"
            points = []

            for p in space.get("points", []):
                if "dx" in p and "dy" in p:
                    points.append(
                        {
                            "dx": round(float(p["dx"]), 3),
                            "dy": round(float(p["dy"]), 3),
                        }
                    )
                else:
                    points.append(
                        {
                            "dx": round(float(p["x"]) - lx, 3),
                            "dy": round(float(p["y"]) - ly, 3),
                        }
                    )

            payload_slots = []
            for slot in space.get("payload_slots", []):
                if not isinstance(slot, dict):
                    continue
                payload_name = str(slot.get("payload", "")).strip()
                if not payload_name:
                    continue
                clean_slot = {
                    "payload": payload_name,
                    "rotation_deg": round(
                        float(slot.get("rotation_deg", 0.0) or 0.0), 3
                    ),
                }
                if "dx" in slot and "dy" in slot:
                    clean_slot["dx"] = round(float(slot.get("dx", 0.0)), 3)
                    clean_slot["dy"] = round(float(slot.get("dy", 0.0)), 3)
                else:
                    clean_slot["dx"] = round(float(slot.get("x", lx)) - lx, 3)
                    clean_slot["dy"] = round(float(slot.get("y", ly)) - ly, 3)
                payload_slots.append(clean_slot)

            if len(points) >= 3:
                clean_spaces.append(
                    {
                        "name": name,
                        "points": points,
                        "payload_slots": payload_slots,
                    }
                )

        location["inventory_spaces"] = clean_spaces

    def inventory_space_points_absolute(self, location_name: str, space: dict) -> list:
        location = self.get_location(location_name)
        if not location:
            return []

        lx = float(location.get("x", 0.0))
        ly = float(location.get("y", 0.0))

        result = []
        for p in space.get("points", []):
            if "dx" in p and "dy" in p:
                result.append(
                    {
                        "x": round(lx + float(p["dx"]), 3),
                        "y": round(ly + float(p["dy"]), 3),
                    }
                )
            else:
                result.append(
                    {
                        "x": round(float(p["x"]), 3),
                        "y": round(float(p["y"]), 3),
                    }
                )

        return result

    def is_department_point(self, name: str) -> bool:
        for dept in self.data.get("departments", []):
            if str(dept.get("name", "")).strip() == str(name).strip():
                return True
        return False

    def add_edge(self, from_name: str, to_name: str) -> None:
        if self.is_department_point(from_name) or self.is_department_point(to_name):
            return
        edges = self.data["corridors"]["edges"]
        if not any(e["from"] == from_name and e["to"] == to_name for e in edges):
            edges.append({"from": from_name, "to": to_name})

    def remove_edge(self, from_name: str, to_name: str) -> None:
        self.data["corridors"]["edges"] = [
            e
            for e in self.data["corridors"]["edges"]
            if not (e["from"] == from_name and e["to"] == to_name)
        ]

    def set_point_position(self, name: str, x: float, y: float) -> None:
        x = round(x, 3)
        y = round(y, 3)
        for item in self.data.get("locations", []):
            if item["name"] == name:
                item["x"] = x
                item["y"] = y
                return
        for item in self.data.get("corridors", {}).get("nodes", []):
            if item["name"] == name:
                item["x"] = x
                item["y"] = y
                return
        for item in self.data.get("departments", []):
            if str(item.get("name", "")) == name:
                item["x"] = x
                item["y"] = y
                return

        if "-F" in name:
            lift_id, floor_text = name.rsplit("-F", 1)
            for lift in self.data.get("lifts", []):
                if lift["id"] == lift_id and floor_text in lift.get(
                    "floor_locations", {}
                ):
                    lift["floor_locations"][floor_text]["x"] = x
                    lift["floor_locations"][floor_text]["y"] = y
                    return

    def rename_point(self, old_name: str, new_name: str) -> None:
        if old_name == new_name:
            return
        for item in self.data.get("locations", []):
            if item["name"] == old_name:
                item["name"] = new_name
        for item in self.data.get("corridors", {}).get("nodes", []):
            if item["name"] == old_name:
                item["name"] = new_name
        for edge in self.data.get("corridors", {}).get("edges", []):
            if edge["from"] == old_name:
                edge["from"] = new_name
            if edge["to"] == old_name:
                edge["to"] = new_name
        for item in self.data.get("departments", []):
            if str(item.get("name", "")) == old_name:
                item["name"] = new_name
            item["waste_pickup_locations"] = [
                new_name if x == old_name else x
                for x in item.get("waste_pickup_locations", [])
            ]
            waste_cfg = item.get("waste", {}) or {}
            if waste_cfg.get("pickup_location") == old_name:
                waste_cfg["pickup_location"] = new_name
            if waste_cfg.get("dropoff_location") == old_name:
                waste_cfg["dropoff_location"] = new_name
        for task in self.data.get("tasks", []):
            if task.get("pickup") == old_name:
                task["pickup"] = new_name
            if task.get("dropoff") == old_name:
                task["dropoff"] = new_name
        for profile in self.data.get("route_profiles", {}).values():
            profile["allowed_nodes"] = [
                new_name if x == old_name else x
                for x in profile.get("allowed_nodes", [])
            ]
            profile["allowed_edges"] = [
                [new_name if part == old_name else part for part in edge_pair]
                for edge_pair in profile.get("allowed_edges", [])
            ]

    def delete_point(self, name: str) -> None:
        self.data["locations"] = [
            x for x in self.data.get("locations", []) if x["name"] != name
        ]
        self.data["corridors"]["nodes"] = [
            x
            for x in self.data.get("corridors", {}).get("nodes", [])
            if x["name"] != name
        ]
        self.data["corridors"]["edges"] = [
            e
            for e in self.data.get("corridors", {}).get("edges", [])
            if e["from"] != name and e["to"] != name
        ]
        self.data["departments"] = [
            x
            for x in self.data.get("departments", [])
            if str(x.get("name", "")) != name
        ]
        for profile in self.data.get("route_profiles", {}).values():
            profile["allowed_nodes"] = [
                x for x in profile.get("allowed_nodes", []) if x != name
            ]
            profile["allowed_edges"] = [
                pair for pair in profile.get("allowed_edges", []) if name not in pair
            ]

    def suggest_next_department_id(self) -> str:
        nums = []
        for item in self.data.get("departments", []):
            dept_id = str(item.get("id", "")).strip().upper()
            if dept_id.startswith("D") and dept_id[1:].isdigit():
                nums.append(int(dept_id[1:]))
        next_num = (max(nums) + 1) if nums else 1
        return f"D{next_num}"

    def upsert_department(self, payload: dict) -> None:
        items = self.data.setdefault("departments", [])
        dept_id = str(payload.get("id", "")).strip()
        existing = next(
            (x for x in items if str(x.get("id", "")).strip() == dept_id),
            None,
        )
        if existing is None:
            items.append(payload)
        else:
            existing.clear()
            existing.update(payload)

    def delete_department(self, dept_id: str) -> None:
        self.data["departments"] = [
            x
            for x in self.data.get("departments", [])
            if str(x.get("id", "")).strip() != str(dept_id).strip()
        ]

    def upsert_waste_stream(self, payload: dict) -> None:
        items = self.data.setdefault("waste_streams", [])
        name = str(payload.get("name", "")).strip()
        existing = next(
            (x for x in items if str(x.get("name", "")).strip() == name),
            None,
        )
        if existing is None:
            items.append(payload)
        else:
            existing.clear()
            existing.update(payload)

    def delete_waste_stream(self, name: str) -> None:
        name = str(name).strip()
        self.data["waste_streams"] = [
            x
            for x in self.data.get("waste_streams", [])
            if str(x.get("name", "")).strip() != name
        ]
        for dept in self.data.get("departments", []):
            dept["waste_streams"] = [
                x for x in dept.get("waste_streams", []) if str(x).strip() != name
            ]

    def upsert_lift(
        self,
        lift_id: str,
        served_floors: List[int],
        floor_locations: Dict[int, Tuple[float, float]],
        speed_floors_per_sec: float = 0.45,
        door_time_sec: float = 4,
        boarding_time_sec: float = 6,
        capacity_length_m: float = 1.0,
        capacity_width_m: float = 1.0,
        capacity_height_m: float = 2.0,
        health_percent: float = 100.0,
        health_loss_per_journey_percent: float = 0.05,
        mean_time_between_failures_hours: float = 720.0,
        mean_time_to_repair_hours: float = 4.0,
        start_floor: int = 0,
    ) -> None:
        lift = None
        for existing in self.data["lifts"]:
            if existing["id"] == lift_id:
                lift = existing
                break

        payload = {
            "id": lift_id,
            "served_floors": sorted(served_floors),
            "speed_floors_per_sec": speed_floors_per_sec,
            "door_time_sec": door_time_sec,
            "boarding_time_sec": boarding_time_sec,
            "capacity_length_m": capacity_length_m,
            "capacity_width_m": capacity_width_m,
            "capacity_height_m": capacity_height_m,
            "health_percent": round(float(health_percent), 3),
            "health_loss_per_journey_percent": round(
                float(health_loss_per_journey_percent), 3
            ),
            "mean_time_between_failures_hours": round(
                float(mean_time_between_failures_hours), 3
            ),
            "mean_time_to_repair_hours": round(float(mean_time_to_repair_hours), 3),
            "start_floor": start_floor,
            "floor_locations": {
                str(f): {"x": round(pos[0], 3), "y": round(pos[1], 3)}
                for f, pos in floor_locations.items()
            },
        }
        if lift is None:
            self.data["lifts"].append(payload)
        else:
            lift.clear()
            lift.update(payload)

    def delete_lift(self, lift_id: str) -> None:
        names_to_delete = {
            f"{lift_id}-F{floor}"
            for lift in self.data.get("lifts", [])
            if lift["id"] == lift_id
            for floor in lift.get("floor_locations", {}).keys()
        }
        self.data["lifts"] = [
            x for x in self.data.get("lifts", []) if x["id"] != lift_id
        ]
        self.data["corridors"]["edges"] = [
            e
            for e in self.data.get("corridors", {}).get("edges", [])
            if e["from"] not in names_to_delete and e["to"] not in names_to_delete
        ]
        for profile in self.data.get("route_profiles", {}).values():
            profile["allowed_lifts"] = [
                x for x in profile.get("allowed_lifts", []) if x != lift_id
            ]
            profile["allowed_nodes"] = [
                x for x in profile.get("allowed_nodes", []) if x not in names_to_delete
            ]
            profile["allowed_edges"] = [
                pair
                for pair in profile.get("allowed_edges", [])
                if not any(name in pair for name in names_to_delete)
            ]

    def validate(self) -> List[str]:
        errors = []
        names = self.names_in_use()

        for edge in self.data.get("corridors", {}).get("edges", []):
            if edge["from"] not in names:
                errors.append(f"Unknown edge start: {edge['from']}")
            if edge["to"] not in names:
                errors.append(f"Unknown edge end: {edge['to']}")

        location_names = {x["name"] for x in self.data.get("locations", [])}
        payload_names = {x["name"] for x in self.data.get("payloads", [])}
        waste_stream_names = {x["name"] for x in self.data.get("waste_streams", [])}
        route_profile_names = set(self.data.get("route_profiles", {}).keys())
        lift_names = {x["id"] for x in self.data.get("lifts", [])}

        for task in self.data.get("tasks", []):
            if (
                task.get("pickup") not in location_names
                and task.get("pickup") not in names
            ):
                errors.append(
                    f"Task {task.get('id')} pickup not found: {task.get('pickup')}"
                )
            if (
                task.get("dropoff") not in location_names
                and task.get("dropoff") not in names
            ):
                errors.append(
                    f"Task {task.get('id')} dropoff not found: {task.get('dropoff')}"
                )
            if task.get("payload") not in payload_names:
                errors.append(
                    f"Task {task.get('id')} payload not found: {task.get('payload')}"
                )
            rp = task.get("route_profile", "")
            if rp and rp not in route_profile_names:
                errors.append(f"Task {task.get('id')} route profile not found: {rp}")

        for profile_name, profile in self.data.get("route_profiles", {}).items():
            for lift_id in profile.get("allowed_lifts", []):
                if lift_id not in lift_names:
                    errors.append(
                        f"Route profile {profile_name} has unknown lift: {lift_id}"
                    )
            for node_name in profile.get("allowed_nodes", []):
                if node_name not in names and node_name not in location_names:
                    errors.append(
                        f"Route profile {profile_name} has unknown node: {node_name}"
                    )
            for edge_pair in profile.get("allowed_edges", []):
                if len(edge_pair) != 2:
                    errors.append(
                        f"Route profile {profile_name} has invalid edge pair: {edge_pair}"
                    )
                    continue
                if edge_pair[0] not in names or edge_pair[1] not in names:
                    errors.append(
                        f"Route profile {profile_name} has unknown edge endpoint: {edge_pair}"
                    )

        for stream in self.data.get("waste_streams", []):
            stream_name = str(stream.get("name", "")).strip()
            if not stream_name:
                errors.append("Waste stream has no name")
            payload_name = str(stream.get("payload", "")).strip()
            if payload_name not in payload_names:
                errors.append(
                    f"Waste stream {stream_name or '-'} payload not found: {payload_name}"
                )
            try:
                capacity = float(stream.get("container_capacity_m3", 0))
                if capacity <= 0:
                    errors.append(
                        f"Waste stream {stream_name or '-'} container capacity must be greater than 0"
                    )
            except Exception:
                errors.append(
                    f"Waste stream {stream_name or '-'} has invalid container capacity"
                )
            try:
                threshold = float(stream.get("full_threshold_fraction", 0))
                if not (0.0 < threshold <= 1.0):
                    errors.append(
                        f"Waste stream {stream_name or '-'} full threshold must be between 0 and 1"
                    )
            except Exception:
                errors.append(
                    f"Waste stream {stream_name or '-'} has invalid full threshold"
                )

        for dept in self.data.get("departments", []):
            dept_name = (
                str(dept.get("name", "")).strip() or str(dept.get("id", "")).strip()
            )
            waste = dept.get("waste", {}) or {}

            for loc in dept.get("waste_pickup_locations", []):
                if loc not in location_names:
                    errors.append(
                        f"Department {dept_name} has unknown waste pickup location: {loc}"
                    )

            for stream_item in dept.get("waste_streams", []):
                if isinstance(stream_item, dict):
                    stream_name = str(stream_item.get("name", "")).strip()
                else:
                    stream_name = str(stream_item).strip()

                if stream_name not in waste_stream_names:
                    errors.append(
                        f"Department {dept_name} has unknown waste stream: {stream_name}"
                    )

            pickup_location = str(waste.get("pickup_location", "")).strip()
            if pickup_location and pickup_location not in location_names:
                errors.append(
                    f"Department {dept_name} has unknown waste pickup location: {pickup_location}"
                )

            dropoff_location = str(waste.get("dropoff_location", "")).strip()
            if dropoff_location and dropoff_location not in location_names:
                errors.append(
                    f"Department {dept_name} has unknown waste dropoff location: {dropoff_location}"
                )

        for amr in self.data.get("amrs", []):
            if (
                amr.get("start_location")
                and amr["start_location"] not in names
                and amr["start_location"] not in location_names
            ):
                errors.append(
                    f"AMR {amr.get('id')} has unknown start location: {amr.get('start_location')}"
                )

            slots = normalise_amr_payload_slots(amr)
            if not slots:
                errors.append(
                    f"AMR {amr.get('id')} must have at least one payload slot"
                )
            for slot in slots:
                slot_name = slot.get("name", "Slot")
                try:
                    if float(slot.get("payload_capacity_kg", 0.0)) <= 0:
                        errors.append(
                            f"AMR {amr.get('id')} {slot_name} payload kg must be greater than 0"
                        )
                    for key, label in [
                        ("payload_length_capacity_m", "length"),
                        ("payload_width_capacity_m", "width"),
                        ("payload_height_capacity_m", "height"),
                    ]:
                        if float(slot.get(key, 0.0)) <= 0:
                            errors.append(
                                f"AMR {amr.get('id')} {slot_name} {label} capacity must be greater than 0"
                            )
                except Exception:
                    errors.append(
                        f"AMR {amr.get('id')} {slot_name} has invalid payload slot dimensions"
                    )

        seen_floors = set()
        for entry in self.data.get("floor_dxf_files", []):
            if not isinstance(entry, dict):
                errors.append(f"Invalid floor_dxf_files entry: {entry}")
                continue

            if "floor" not in entry:
                errors.append("DXF mapping is missing floor")
                continue

            if "filepath" not in entry:
                errors.append(
                    f"DXF mapping for floor {entry.get('floor')} is missing filepath"
                )
                continue

            try:
                floor = int(entry.get("floor"))
            except Exception:
                errors.append(f"DXF mapping has invalid floor: {entry.get('floor')}")
                continue

            filepath = str(entry.get("filepath") or "").strip()
            if not filepath:
                errors.append(f"DXF mapping for floor {floor} has empty filepath")

            if floor in seen_floors:
                errors.append(f"Duplicate DXF mapping for floor {floor}")
            seen_floors.add(floor)

        return errors

    def suggest_next_corridor_name(self, floor: int) -> str:
        prefix = f"C{floor}-"
        nums = []
        for item in self.data.get("corridors", {}).get("nodes", []):
            name = item["name"]
            if name.startswith(prefix):
                tail = name[len(prefix) :]
                if tail.isdigit():
                    nums.append(int(tail))
        next_num = max(nums, default=0) + 1
        return f"C{floor}-{next_num}"

    def suggest_next_task_id(self) -> str:
        nums = []
        for task in self.data.get("tasks", []):
            task_id = str(task.get("id", ""))
            if task_id.startswith("T") and task_id[1:].isdigit():
                nums.append(int(task_id[1:]))
        return f"T{max(nums, default=0) + 1}"

    @staticmethod
    def basename(path: Optional[str]) -> str:
        if not path:
            return "New file"
        return Path(path).name
