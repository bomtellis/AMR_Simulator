"""
Automatic task generation for the AMR simulator.

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from amr_sim_models import Location, PayloadType, Task
from amr_sim_time_utils import SimulationClock

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SCHEDULED_MODES = {"scheduled", "scheduled_threshold", "scheduled_sporadic"}
THRESHOLD_MODES = {"threshold", "hybrid", "scheduled_threshold"}
CONTINUOUS_MODES = {"continuous", "hybrid", "threshold", "scheduled_threshold"}
SPORADIC_MODES = {"sporadic", "hybrid", "scheduled_sporadic"}


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


def _clean_text(value) -> str:
    return str(value or "").strip()


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _unique_clean(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = _clean_text(value)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _scheduled_times_from_cfg(cfg: dict) -> List[str]:
    values = cfg.get("scheduled_times", cfg.get("schedule_times", []))
    if isinstance(values, str):
        values = [x.strip() for x in values.split(",")]
    clean = []
    for value in values or []:
        text = _clean_text(value)
        if not text:
            continue
        # Accept HH:MM and HH:MM:SS, normalise to HH:MM.
        try:
            parts = [int(x) for x in text.split(":")[:2]]
            if len(parts) == 2 and 0 <= parts[0] <= 23 and 0 <= parts[1] <= 59:
                clean.append(f"{parts[0]:02d}:{parts[1]:02d}")
        except Exception:
            continue
    return sorted(set(clean))


def _day_key_for_datetime(value: datetime) -> str:
    return DAY_KEYS[value.weekday()]


def _datetime_for_day_and_hhmm(day_start: datetime, hhmm: str) -> datetime:
    hour, minute = [int(x) for x in hhmm.split(":")[:2]]
    return datetime.combine(day_start.date(), dt_time(hour=hour, minute=minute))


def _payload_tracked_items(payload: Optional[PayloadType]) -> Dict[str, dict]:
    if payload is None or not getattr(payload, "track_items", False):
        return {}
    items = getattr(payload, "items", {}) or {}
    if not isinstance(items, dict):
        return {}

    result: Dict[str, dict] = {}
    for name, cfg in items.items():
        if not isinstance(cfg, dict):
            continue
        item_name = _clean_text(name)
        if not item_name:
            continue
        result[item_name] = {
            "target_quantity": _as_float(cfg.get("max", 100), 100),
            "trigger_quantity": _as_float(cfg.get("top_up_threshold", 15), 15),
            "usage_rate": _clean_text(cfg.get("usage_rate", "scheduled_sporadic"))
            or "scheduled_sporadic",
            "consumption_per_day": _as_float(cfg.get("consumption_per_day", 0.0), 0.0),
            "exchange_payload": _clean_text(cfg.get("exchange_payload", "")),
            "source_location": _clean_text(cfg.get("source_location", "")),
        }
    return result


def _apply_tracked_item_metadata(
    task: Task, cfg: dict, payloads: Dict[str, PayloadType]
) -> None:
    if not bool(cfg.get("tracked_item_exchange", False)):
        return

    base_payload_name = _clean_text(cfg.get("payload", task.payload))
    base_payload = payloads.get(base_payload_name)
    tracked_items = _payload_tracked_items(base_payload)
    if not tracked_items:
        return

    task.tracked_item_exchange = True
    task.exchange_mode = (
        _clean_text(cfg.get("exchange_mode", "top_up_only")) or "top_up_only"
    )
    task.tracked_item_source_payload = base_payload_name
    task.tracked_items = tracked_items

    # If every tracked item points to the same source or payload, use it as a more
    # specific task instruction. Mixed item sources remain as task metadata only.
    source_locations = {
        _clean_text(item.get("source_location", ""))
        for item in tracked_items.values()
        if _clean_text(item.get("source_location", ""))
    }
    exchange_payloads = {
        _clean_text(item.get("exchange_payload", ""))
        for item in tracked_items.values()
        if _clean_text(item.get("exchange_payload", ""))
    }

    if len(source_locations) == 1:
        task.pickup = next(iter(source_locations))
    if len(exchange_payloads) == 1:
        task.payload = next(iter(exchange_payloads))


class DynamicCategoryTaskGenerator(BaseTaskGenerator):
    """
    Generates tasks from task_generation.categories.

    This is the simulator-side counterpart of the editor's task generation dialog.
    It honours category defaults, department overrides and per-department location
    assignments created in the department dialog.
    """

    generator_type = "dynamic_category"

    def __init__(
        self,
        task_generation: dict,
        departments: Iterable[dict],
        locations: Dict[str, Location],
        payloads: Dict[str, PayloadType],
        clock: SimulationClock,
        waste_streams: Optional[Dict[str, dict]] = None,
    ):
        self.task_generation = task_generation or {}
        self.departments = list(departments or [])
        self.locations = locations or {}
        self.payloads = payloads or {}
        self.clock = clock
        self.waste_streams = waste_streams or {}
        self.task_counter = 0
        self.return_counter = 0
        self.scheduled_emitted = set()
        self.runtime: Dict[str, dict] = {}
        self.item_runtime: Dict[str, dict] = {}
        self.instances = self._build_instances()

    def _next_task_id(self, category_key: str, department_id: str = "") -> str:
        self.task_counter += 1
        safe_cat = "".join(
            c if c.isalnum() else "_" for c in category_key.upper()
        ).strip("_")
        safe_dept = "".join(
            c if c.isalnum() else "_" for c in department_id.upper()
        ).strip("_")
        if safe_dept:
            return f"GEN_{safe_cat}_{safe_dept}_{self.task_counter:05d}"
        return f"GEN_{safe_cat}_{self.task_counter:05d}"

    def _next_return_task_id(self, outbound_id: str) -> str:
        self.return_counter += 1
        safe = "".join(c if c.isalnum() else "_" for c in outbound_id.upper()).strip(
            "_"
        )
        return f"RETURN_{safe}_{self.return_counter:05d}"

    def _category_is_active(self, cfg: dict, sim_time_sec: float) -> bool:
        if not bool(cfg.get("enabled", False)):
            return False
        active_days = cfg.get("days_active", []) or []
        if active_days:
            allowed = {_clean_text(x).lower() for x in active_days if _clean_text(x)}
            if self._day_key_for_sim_time(sim_time_sec) not in allowed:
                return False
        return True

    def _day_key_for_sim_time(self, sim_time_sec: float) -> str:
        return _day_key_for_datetime(self.clock.sim_seconds_to_datetime(sim_time_sec))

    def _merge_category_with_override(
        self, category: dict, override: Optional[dict]
    ) -> dict:
        merged = dict(category or {})
        merged.pop("departments", None)
        if isinstance(override, dict):
            merged.update(override)
        return merged

    def _department_id(self, dept: dict) -> str:
        return _clean_text(dept.get("id")) or _clean_text(dept.get("name"))

    def _department_name(self, dept: dict) -> str:
        return _clean_text(dept.get("name")) or self._department_id(dept)

    def _department_category_locations(
        self, dept: dict, category_key: str
    ) -> List[str]:
        category_locations = dept.get("task_generation_locations", {}) or {}
        entry = category_locations.get(category_key, {}) or {}
        values = entry.get("pickup_dropoff_locations", [])
        return _unique_clean(values)

    def _dropoff_locations_from_cfg(self, cfg: dict) -> List[str]:
        values = []
        if isinstance(cfg.get("dropoff_locations"), list):
            values.extend(cfg.get("dropoff_locations", []))
        if cfg.get("dropoff_location"):
            values.insert(0, cfg.get("dropoff_location"))
        return _unique_clean(values)

    def _pickup_locations_from_cfg(self, cfg: dict) -> List[str]:
        values = []
        if isinstance(cfg.get("pickup_locations"), list):
            values.extend(cfg.get("pickup_locations", []))
        if cfg.get("pickup_location"):
            values.insert(0, cfg.get("pickup_location"))
        return _unique_clean(values)

    def _department_waste_stream_items(self, dept: dict) -> List[dict]:
        """Return configured waste stream entries for a department.

        Waste is the only logistics category that expands one configured
        department/category override into per-stream generator instances.  The
        department dialog stores waste streams as either names or dictionaries
        containing per-department generation settings.  This normalises both
        forms and ignores blank entries.
        """
        result: List[dict] = []
        seen = set()

        for raw in dept.get("waste_streams", []) or []:
            if isinstance(raw, dict):
                item = dict(raw)
                name = _clean_text(item.get("name"))
            else:
                name = _clean_text(raw)
                item = {"name": name}

            if not name or name in seen:
                continue

            item["name"] = name
            result.append(item)
            seen.add(name)

        return result

    def _threshold_from_waste_stream(self, stream_name: str, cfg: dict) -> float:
        threshold = _as_float(cfg.get("threshold_volume_m3", 0.0), 0.0)
        if threshold > 0:
            return threshold

        stream_cfg = self.waste_streams.get(stream_name, {}) or {}
        capacity = _as_float(stream_cfg.get("container_capacity_m3", 0.0), 0.0)
        fraction = _as_float(stream_cfg.get("full_threshold_fraction", 0.8), 0.8)
        fallback = capacity * fraction
        return fallback if fallback > 0 else 0.0

    def _waste_container_group_for_instance(
        self, dept_id: str, stream_name: str, cfg: dict, pickup_locations: List[str]
    ) -> str:
        explicit = _clean_text(
            cfg.get("shared_container_group", cfg.get("shared_container_id", ""))
        )
        if explicit:
            return f"shared:{explicit}"
        if bool(cfg.get("shared_container", False)):
            pickup_signature = ",".join(sorted(_unique_clean(pickup_locations)))
            return f"pickup:{stream_name}:{pickup_signature}"
        return f"department:{dept_id}:{stream_name}"

    def _waste_stream_cfg_for_department(
        self, category_cfg: dict, dept_override: dict, stream_item: dict
    ) -> Optional[dict]:
        stream_name = _clean_text(stream_item.get("name"))
        if not stream_name:
            return None

        global_stream = dict(self.waste_streams.get(stream_name, {}) or {})

        # Deleted/orphaned stream assignments should be removable in the UI but
        # should not create new tasks unless they still carry a valid payload in
        # the saved department stream item.
        if stream_name not in self.waste_streams and not _clean_text(
            stream_item.get("payload")
        ):
            return None

        cfg = self._merge_category_with_override(category_cfg, dept_override)

        # Global stream definition supplies the container/payload defaults.
        for key in ("payload", "container_capacity_m3", "full_threshold_fraction"):
            if key in global_stream and _clean_text(global_stream.get(key)):
                cfg[key] = global_stream.get(key)

        # The department's selected stream item supplies generation settings and
        # may intentionally override the global stream payload if present.
        for key, value in stream_item.items():
            if key == "name":
                continue
            cfg[key] = value

        cfg["waste_stream"] = stream_name
        cfg["task_source"] = "department_waste"
        cfg["initial_container_present"] = bool(
            cfg.get("initial_container_present", True)
        )
        cfg["shared_container"] = bool(cfg.get("shared_container", False))
        cfg["shared_container_group"] = _clean_text(
            cfg.get("shared_container_group", cfg.get("shared_container_id", ""))
        )

        payload_name = _clean_text(cfg.get("payload", ""))
        if not payload_name:
            payload_name = _clean_text(global_stream.get("payload", ""))
            cfg["payload"] = payload_name

        if payload_name not in self.payloads:
            return None

        threshold = self._threshold_from_waste_stream(stream_name, cfg)
        if threshold > 0:
            cfg["threshold_volume_m3"] = threshold

        if _as_float(cfg.get("volume_per_event_m3", 0.0), 0.0) <= 0.0:
            cfg["volume_per_event_m3"] = threshold

        return cfg

    def _build_instances(self) -> List[dict]:
        categories = self.task_generation.get("categories", {}) or {}
        instances: List[dict] = []

        for category_key, category in categories.items():
            if not isinstance(category, dict):
                continue

            category_key_text = str(category_key)
            overrides = (
                category.get("departments", {})
                if isinstance(category.get("departments", {}), dict)
                else {}
            )

            # Department overrides are independently enabled.  The category
            # default "enabled" flag must not disable configured departments.
            # Waste is the only category that expands into one instance per
            # configured department waste stream.
            for dept in self.departments:
                dept_id = self._department_id(dept)
                if not dept_id or dept_id not in overrides:
                    continue

                override = overrides.get(dept_id, {})
                cfg = self._merge_category_with_override(category, override)
                if not bool(cfg.get("enabled", False)):
                    continue

                dept_locations = self._department_category_locations(
                    dept, category_key_text
                )
                role = (
                    _clean_text(cfg.get("department_location_role", "dropoff"))
                    or "dropoff"
                )

                pickup_locations = self._pickup_locations_from_cfg(cfg)
                dropoff_locations = self._dropoff_locations_from_cfg(cfg)

                if role == "pickup" and dept_locations:
                    pickup_locations = dept_locations
                elif role != "pickup" and dept_locations:
                    dropoff_locations = dept_locations

                if category_key_text.lower() == "waste":
                    stream_items = self._department_waste_stream_items(dept)

                    if stream_items:
                        for stream_item in stream_items:
                            stream_cfg = self._waste_stream_cfg_for_department(
                                category, override, stream_item
                            )
                            if not stream_cfg:
                                continue
                            stream_name = _clean_text(stream_cfg.get("waste_stream"))
                            container_group = self._waste_container_group_for_instance(
                                dept_id, stream_name, stream_cfg, pickup_locations
                            )
                            stream_cfg["container_group"] = container_group
                            unique_key = f"waste:{dept_id}:{stream_name}"
                            instances.append(
                                {
                                    "key": unique_key,
                                    "volume_key": container_group,
                                    "schedule_key": container_group,
                                    "category_key": "waste",
                                    "department_id": dept_id,
                                    "department_name": self._department_name(dept),
                                    "cfg": stream_cfg,
                                    "pickup_locations": pickup_locations,
                                    "dropoff_locations": dropoff_locations,
                                    "waste_stream": stream_name,
                                    "container_group": container_group,
                                }
                            )
                        continue

                    # Backwards compatibility: if no department streams are set,
                    # use the old department waste category override.

                instances.append(
                    {
                        "key": f"{category_key_text}:{dept_id}",
                        "category_key": category_key_text,
                        "department_id": dept_id,
                        "department_name": self._department_name(dept),
                        "cfg": cfg,
                        "pickup_locations": pickup_locations,
                        "dropoff_locations": dropoff_locations,
                    }
                )

            # Category-level generation is only for a deliberately enabled
            # category default and only when there are no department overrides.
            # This prevents the "Category defaults" row from creating a site-wide
            # task in addition to department-level tasks.
            if bool(category.get("enabled", False)) and not overrides:
                instances.append(
                    {
                        "key": category_key_text,
                        "category_key": category_key_text,
                        "department_id": "",
                        "department_name": "",
                        "cfg": self._merge_category_with_override(category, None),
                        "pickup_locations": self._pickup_locations_from_cfg(category),
                        "dropoff_locations": self._dropoff_locations_from_cfg(category),
                    }
                )

        return instances

    def _valid_locations_and_payload(
        self, pickup: str, dropoff: str, payload: str
    ) -> bool:
        return bool(
            pickup in self.locations
            and dropoff in self.locations
            and payload in self.payloads
        )

    def _base_task(
        self,
        instance: dict,
        pickup: str,
        dropoff: str,
        payload_name: str,
        release_time: float,
        label_suffix: str = "",
    ) -> Optional[Task]:
        cfg = instance["cfg"]
        if not self._valid_locations_and_payload(pickup, dropoff, payload_name):
            return None

        category_key = instance["category_key"]
        department_id = instance.get("department_id", "")
        labels = [category_key]
        if department_id:
            labels.append(department_id)
        if label_suffix:
            labels.append(label_suffix)

        task = Task(
            id=self._next_task_id(category_key, department_id),
            pickup=pickup,
            dropoff=dropoff,
            payload=payload_name,
            release_time=release_time,
            target_time=_as_float(cfg.get("target_time", 0.0), 0.0),
            quantity=1,
            priority=_as_int(cfg.get("priority", 100), 100),
            created_during_runtime=True,
            labels=labels,
            route_profile=_clean_text(cfg.get("route_profile")) or None,
            task_source=_clean_text(cfg.get("task_source", "task_generation"))
            or "task_generation",
            department_id=department_id,
            waste_stream=_clean_text(cfg.get("waste_stream", "")),
            waste_volume_m3=_as_float(cfg.get("waste_volume_m3", 0.0), 0.0),
            container_type=payload_name,
        )
        if bool(cfg.get("return_enabled", False)):
            return_payload = _clean_text(cfg.get("return_payload", ""))
            if return_payload in self.payloads:
                task.return_enabled = True
                task.return_payload = return_payload
                task.return_delay_minutes = _as_float(
                    cfg.get("return_delay_minutes", 0.0), 0.0
                )
                task.return_route_profile = _clean_text(
                    cfg.get("return_route_profile", cfg.get("route_profile", ""))
                )
                task.return_priority = _as_int(
                    cfg.get("return_priority", cfg.get("priority", 100)), 100
                )

        # Waste-only runtime metadata.  These are deliberately attached as
        # dynamic attributes so amr_sim_models.Task remains backwards-compatible.
        # The simulator uses them to decide whether generated waste tasks must
        # collect an existing seeded container and whether several departments
        # share the same physical bin.
        if _clean_text(cfg.get("waste_stream", "")) or (
            _clean_text(cfg.get("task_source", "")) == "department_waste"
        ):
            task.initial_container_present = bool(
                cfg.get("initial_container_present", True)
            )
            task.shared_container = bool(cfg.get("shared_container", False))
            task.shared_container_group = _clean_text(
                cfg.get("shared_container_group", cfg.get("shared_container_id", ""))
            )
            task.container_group = _clean_text(cfg.get("container_group", ""))

        _apply_tracked_item_metadata(task, cfg, self.payloads)

        # Metadata may override pickup/payload using item-specific source/payload.
        if task.pickup not in self.locations or task.payload not in self.payloads:
            return None
        return task

    def _record_for_task(
        self, task: Task, instance: dict, event_type: str, details: str
    ) -> GeneratedTaskRecord:
        return GeneratedTaskRecord(
            task=task,
            event_type=event_type,
            details=details,
            pickup_location=task.pickup,
            dropoff_location=task.dropoff,
            payload_name=task.payload,
            task_source=getattr(task, "task_source", "task_generation"),
            department_id=getattr(
                task, "department_id", instance.get("department_id", "")
            ),
            waste_stream=getattr(
                task, "waste_stream", instance.get("waste_stream", "")
            ),
            waste_volume_m3=float(
                getattr(
                    task,
                    "waste_volume_m3",
                    getattr(task, "generated_volume_m3", 0.0),
                )
                or getattr(task, "generated_volume_m3", 0.0)
                or 0.0
            ),
            container_type=task.payload,
        )

    def _create_return_task(self, outbound: Task, instance: dict) -> Optional[Task]:
        cfg = instance["cfg"]
        if not bool(cfg.get("return_enabled", False)):
            return None

        return_payload = _clean_text(cfg.get("return_payload", ""))
        if not return_payload:
            # Deliberately do not invent a payload. Use a configured "none" payload if
            # you need empty returns.
            return None
        if return_payload not in self.payloads:
            return None

        delay_minutes = _as_float(cfg.get("return_delay_minutes", 0.0), 0.0)
        release_time = outbound.release_time + (delay_minutes * 60.0)

        task = Task(
            id=self._next_return_task_id(outbound.id),
            pickup=outbound.dropoff,
            dropoff=outbound.pickup,
            payload=return_payload,
            release_time=release_time,
            target_time=_as_float(
                cfg.get("return_target_time", cfg.get("target_time", 0.0)), 0.0
            ),
            quantity=1,
            priority=_as_int(cfg.get("return_priority", cfg.get("priority", 100)), 100),
            created_during_runtime=True,
            labels=list(outbound.labels) + ["return"],
            route_profile=_clean_text(
                cfg.get("return_route_profile", cfg.get("route_profile", ""))
            )
            or None,
            task_source="task_generation_return",
            department_id=getattr(outbound, "department_id", ""),
            container_type=return_payload,
            payload_instance_id=str(getattr(outbound, "payload_instance_id", "") or ""),
            is_return_task=True,
        )
        return task

    def _records_for_outbound(
        self, outbound: Optional[Task], instance: dict, reason: str
    ) -> List[GeneratedTaskRecord]:
        if outbound is None:
            return []
        return [
            self._record_for_task(
                outbound,
                instance,
                "task_generated",
                reason,
            )
        ]

    def _pick_pairs(self, instance: dict) -> List[Tuple[str, str]]:
        pickups = [
            x for x in instance.get("pickup_locations", []) if x in self.locations
        ]
        dropoffs = [
            x for x in instance.get("dropoff_locations", []) if x in self.locations
        ]
        if not pickups or not dropoffs:
            return []
        pairs: List[Tuple[str, str]] = []
        for pickup in pickups:
            for dropoff in dropoffs:
                if pickup != dropoff:
                    pairs.append((pickup, dropoff))
        return pairs

    def _is_waste_instance(self, instance: dict) -> bool:
        cfg = instance.get("cfg", {}) or {}
        return bool(_clean_text(cfg.get("waste_stream", ""))) or (
            _clean_text(cfg.get("task_source", "")) == "department_waste"
        )

    def _runtime_for_volume_key(self, instance: dict) -> dict:
        return self.runtime.setdefault(
            instance.get("volume_key", instance["key"]),
            {
                "volume": 0.0,
                "contributors": {},
                "sporadic_accumulator": {},
                "volume_event_accumulator": {},
            },
        )

    def _threshold_collection_records(
        self, instance: dict, release_time: float, details: str
    ) -> List[GeneratedTaskRecord]:
        cfg = instance["cfg"]
        threshold_volume = _as_float(cfg.get("threshold_volume_m3", 0.0), 0.0)
        if threshold_volume <= 0.0:
            return []

        payload_name = _clean_text(cfg.get("payload", ""))
        if payload_name not in self.payloads:
            return []

        runtime = self._runtime_for_volume_key(instance)
        records: List[GeneratedTaskRecord] = []
        while _as_float(runtime.get("volume", 0.0), 0.0) >= threshold_volume:
            runtime["volume"] = (
                _as_float(runtime.get("volume", 0.0), 0.0) - threshold_volume
            )
            for pickup, dropoff in self._pick_pairs(instance):
                task = self._base_task(
                    instance, pickup, dropoff, payload_name, release_time, "threshold"
                )
                if task is not None:
                    # This is the amount being collected from the bin, not the
                    # individual fill-event volume.  Using volume_per_event_m3
                    # here made threshold collections look like nearly empty bin
                    # swaps in the CSV/visualiser.
                    task.generated_volume_m3 = threshold_volume
                    task.waste_volume_m3 = threshold_volume
                records.extend(self._records_for_outbound(task, instance, details))
        return records

    def _schedule_records(
        self, instance: dict, now: float
    ) -> List[GeneratedTaskRecord]:
        cfg = instance["cfg"]
        mode = _clean_text(cfg.get("generation_mode", "scheduled")) or "scheduled"
        if mode not in SCHEDULED_MODES:
            return []

        payload_name = _clean_text(cfg.get("payload", ""))
        if payload_name not in self.payloads:
            return []

        current_dt = self.clock.sim_seconds_to_datetime(now)
        day_start = current_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        records: List[GeneratedTaskRecord] = []

        for hhmm in _scheduled_times_from_cfg(cfg):
            release_dt = _datetime_for_day_and_hhmm(day_start, hhmm)
            release_time = (release_dt - self.clock.start_datetime).total_seconds()
            if release_time < 0 or release_time > now:
                continue
            if not self._category_is_active(cfg, release_time):
                continue

            schedule_key = (
                instance.get("schedule_key", instance["key"]),
                release_dt.date().isoformat(),
                hhmm,
            )
            if schedule_key in self.scheduled_emitted:
                continue
            self.scheduled_emitted.add(schedule_key)

            if self._is_waste_instance(instance) and mode == "scheduled_threshold":
                # For seeded/physical waste containers a scheduled-threshold entry
                # is a fill event, not an instruction to swap the bin immediately.
                # Only create a collection task when the accumulated fill reaches
                # the threshold.
                runtime = self._runtime_for_volume_key(instance)
                runtime["volume"] = _as_float(runtime.get("volume", 0.0), 0.0) + max(
                    0.0, _as_float(cfg.get("volume_per_event_m3", 0.0), 0.0)
                )
                records.extend(
                    self._threshold_collection_records(
                        instance,
                        release_time,
                        f"Generated scheduled-threshold {instance['category_key']} task at {hhmm}",
                    )
                )
                continue

            for pickup, dropoff in self._pick_pairs(instance):
                task = self._base_task(
                    instance=instance,
                    pickup=pickup,
                    dropoff=dropoff,
                    payload_name=payload_name,
                    release_time=release_time,
                    label_suffix="scheduled",
                )
                if task is not None and _clean_text(cfg.get("waste_stream", "")):
                    task.generated_volume_m3 = _as_float(
                        cfg.get("volume_per_event_m3", 0.0), 0.0
                    )
                    task.waste_volume_m3 = task.generated_volume_m3
                records.extend(
                    self._records_for_outbound(
                        task,
                        instance,
                        f"Generated scheduled {instance['category_key']} task at {hhmm}",
                    )
                )

        return records

    def _volume_records(self, instance: dict, now: float) -> List[GeneratedTaskRecord]:
        cfg = instance["cfg"]
        mode = _clean_text(cfg.get("generation_mode", "scheduled")) or "scheduled"
        if mode not in (THRESHOLD_MODES | CONTINUOUS_MODES | SPORADIC_MODES):
            return []

        payload_name = _clean_text(cfg.get("payload", ""))
        if payload_name not in self.payloads:
            return []
        if not self._category_is_active(cfg, now):
            # Still advance the clock to avoid back-generating when re-entering active time.
            runtime = self.runtime.setdefault(
                instance.get("volume_key", instance["key"]),
                {
                    "volume": 0.0,
                    "contributors": {},
                    "sporadic_accumulator": {},
                    "volume_event_accumulator": {},
                },
            )
            runtime.setdefault("contributors", {})[instance["key"]] = now
            return []

        volume_key = instance.get("volume_key", instance["key"])
        runtime = self.runtime.setdefault(
            volume_key,
            {
                "volume": 0.0,
                "contributors": {},
                "sporadic_accumulator": {},
                "volume_event_accumulator": {},
            },
        )
        contributor_key = instance["key"]
        contributors = runtime.setdefault("contributors", {})
        last_time = _as_float(contributors.get(contributor_key, 0.0), 0.0)
        if now <= last_time:
            return []

        elapsed_days = (now - last_time) / 86400.0
        elapsed_hours = (now - last_time) / 3600.0
        records: List[GeneratedTaskRecord] = []

        if mode in CONTINUOUS_MODES:
            runtime["volume"] += max(
                0.0, elapsed_days * _as_float(cfg.get("base_daily_volume_m3", 0.0), 0.0)
            )

        # For threshold-based waste streams, frequency_per_day and
        # volume_per_event_m3 represent bin-fill events.  The previous dynamic
        # category path only used base_daily_volume_m3, so department stream
        # settings with event volumes never accumulated to the threshold.
        if mode in THRESHOLD_MODES:
            event_frequency = max(
                0.0, _as_float(cfg.get("frequency_per_day", 0.0), 0.0)
            )
            event_volume = max(0.0, _as_float(cfg.get("volume_per_event_m3", 0.0), 0.0))
            if event_frequency > 0.0 and event_volume > 0.0:
                volume_event_accumulators = runtime.setdefault(
                    "volume_event_accumulator", {}
                )
                volume_event_accumulators[contributor_key] = _as_float(
                    volume_event_accumulators.get(contributor_key, 0.0), 0.0
                ) + (elapsed_days * event_frequency)
                whole_events = int(volume_event_accumulators[contributor_key])
                if whole_events > 0:
                    runtime["volume"] += whole_events * event_volume
                    volume_event_accumulators[contributor_key] -= whole_events

        if mode in SPORADIC_MODES:
            freq_per_day = max(0.0, _as_float(cfg.get("frequency_per_day", 0.0), 0.0))
            sporadic_accumulators = runtime.setdefault("sporadic_accumulator", {})
            sporadic_accumulators[contributor_key] = _as_float(
                sporadic_accumulators.get(contributor_key, 0.0), 0.0
            ) + (elapsed_days * freq_per_day)
            while sporadic_accumulators[contributor_key] >= 1.0:
                sporadic_accumulators[contributor_key] -= 1.0
                for pickup, dropoff in self._pick_pairs(instance):
                    task = self._base_task(
                        instance, pickup, dropoff, payload_name, now, "sporadic"
                    )
                    if task is not None:
                        generated_volume = _as_float(
                            cfg.get("volume_per_event_m3", 0.0), 0.0
                        )
                        task.generated_volume_m3 = generated_volume
                        task.waste_volume_m3 = generated_volume
                    records.extend(
                        self._records_for_outbound(
                            task,
                            instance,
                            f"Generated sporadic {instance['category_key']} task",
                        )
                    )

        if mode in THRESHOLD_MODES:
            records.extend(
                self._threshold_collection_records(
                    instance,
                    now,
                    f"Generated threshold {instance['category_key']} task",
                )
            )

        contributors[contributor_key] = now
        return records

    def _tracked_item_records(
        self, instance: dict, now: float
    ) -> List[GeneratedTaskRecord]:
        cfg = instance["cfg"]
        if not bool(cfg.get("tracked_item_exchange", False)):
            return []
        payload_name = _clean_text(cfg.get("payload", ""))
        payload = self.payloads.get(payload_name)
        items = _payload_tracked_items(payload)
        if not items:
            return []
        if not self._category_is_active(cfg, now):
            self.item_runtime.setdefault(
                instance["key"], {"last_update_time": now, "quantities": {}}
            )["last_update_time"] = now
            return []

        runtime = self.item_runtime.setdefault(
            instance["key"],
            {
                "last_update_time": 0.0,
                "quantities": {
                    name: item["target_quantity"] for name, item in items.items()
                },
            },
        )
        quantities = runtime.setdefault("quantities", {})
        for name, item in items.items():
            quantities.setdefault(name, item["target_quantity"])

        last_time = _as_float(runtime.get("last_update_time", 0.0), 0.0)
        if now <= last_time:
            return []

        elapsed_days = (now - last_time) / 86400.0
        triggered: Dict[str, dict] = {}
        for name, item in items.items():
            consumption = max(0.0, item.get("consumption_per_day", 0.0)) * elapsed_days
            quantities[name] = max(
                0.0,
                _as_float(
                    quantities.get(name, item["target_quantity"]),
                    item["target_quantity"],
                )
                - consumption,
            )
            if quantities[name] <= item["trigger_quantity"]:
                triggered[name] = {
                    **item,
                    "current_quantity": round(quantities[name], 3),
                    "target_quantity": item["target_quantity"],
                }
                # Assume an exchange/top-up request resets the local store to full.
                quantities[name] = item["target_quantity"]

        runtime["last_update_time"] = now
        if not triggered:
            return []

        records: List[GeneratedTaskRecord] = []
        exchange_mode = (
            _clean_text(cfg.get("exchange_mode", "top_up_only")) or "top_up_only"
        )

        for pickup, dropoff in self._pick_pairs(instance):
            task_payload = payload_name
            source_locations = {
                _clean_text(item.get("source_location"))
                for item in triggered.values()
                if _clean_text(item.get("source_location"))
            }
            exchange_payloads = {
                _clean_text(item.get("exchange_payload"))
                for item in triggered.values()
                if _clean_text(item.get("exchange_payload"))
            }
            task_pickup = (
                next(iter(source_locations)) if len(source_locations) == 1 else pickup
            )
            if len(exchange_payloads) == 1:
                task_payload = next(iter(exchange_payloads))

            task = self._base_task(
                instance,
                task_pickup,
                dropoff,
                task_payload,
                now,
                "tracked_item_exchange",
            )
            if task is None:
                continue
            task.tracked_item_exchange = True
            task.exchange_mode = exchange_mode
            task.tracked_item_source_payload = payload_name
            task.tracked_items = triggered
            records.extend(
                self._records_for_outbound(
                    task,
                    instance,
                    f"Generated tracked item exchange for {', '.join(sorted(triggered.keys()))}",
                )
            )

        return records

    def update_until(self, now: float) -> List[GeneratedTaskRecord]:
        generated: List[GeneratedTaskRecord] = []
        if not self.instances:
            return generated

        for instance in self.instances:
            generated.extend(self._schedule_records(instance, now))
            generated.extend(self._volume_records(instance, now))
            generated.extend(self._tracked_item_records(instance, now))

        return generated


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
                str(x.get("name", x) if isinstance(x, dict) else x).strip()
                for x in dept.get("waste_streams", [])
                if str(x.get("name", x) if isinstance(x, dict) else x).strip()
                in self.waste_streams
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
            priority=int(
                waste_cfg.get("priority", self.default_priority)
                or self.default_priority
            ),
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

    def _task_generation_cfg(self) -> dict:
        return self.config.get("task_generation", {}) or {}

    def _generation_enabled(self, name: str, default: bool = True) -> bool:
        cfg = self._task_generation_cfg()
        if cfg and not bool(cfg.get("enabled", True)):
            return False
        specific = cfg.get(name, {}) or {}
        return bool(specific.get("enabled", default))

    def _has_dynamic_categories(self) -> bool:
        categories = self._task_generation_cfg().get("categories", {}) or {}
        for category in categories.values():
            if not isinstance(category, dict):
                continue

            # Enabled category default, usually legacy/global category generation.
            if bool(category.get("enabled", False)):
                return True

            # Enabled department overrides must start the dynamic generator even
            # when the category default is intentionally disabled.
            overrides = category.get("departments", {})
            if isinstance(overrides, dict):
                for override in overrides.values():
                    if isinstance(override, dict) and bool(
                        override.get("enabled", False)
                    ):
                        return True
        return False

    def _build_generators(self) -> None:
        task_generation = self._task_generation_cfg()
        departments = list(self.config.get("departments", []))

        waste_streams = {
            str(item.get("name", "")).strip(): dict(item)
            for item in self.config.get("waste_streams", [])
            if str(item.get("name", "")).strip()
        }

        if self._has_dynamic_categories() and bool(
            task_generation.get("enabled", True)
        ):
            self.generators.append(
                DynamicCategoryTaskGenerator(
                    task_generation=task_generation,
                    departments=departments,
                    locations=self.locations,
                    payloads=self.payloads,
                    clock=self.clock,
                    waste_streams=waste_streams,
                )
            )

        # Keep legacy department waste support, but avoid duplicating new waste category
        # generation when the dynamic Waste category is enabled.
        categories = task_generation.get("categories", {}) or {}
        waste_category = (
            categories.get("waste", {})
            if isinstance(categories.get("waste", {}), dict)
            else {}
        )
        waste_overrides = (
            waste_category.get("departments", {})
            if isinstance(waste_category.get("departments", {}), dict)
            else {}
        )
        dynamic_waste_enabled = bool(
            bool(waste_category.get("enabled", False))
            or any(
                isinstance(override, dict) and bool(override.get("enabled", False))
                for override in waste_overrides.values()
            )
        )

        if (
            waste_streams
            and departments
            and not dynamic_waste_enabled
            and self._generation_enabled("department_waste", True)
        ):
            priority = int(
                (task_generation.get("department_waste", {}) or {}).get("priority", 60)
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
