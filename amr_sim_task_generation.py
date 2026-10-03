"""
Automatic task generation for the AMR simulator.

"""

from __future__ import annotations

from dataclasses import dataclass
import math
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from amr_sim_models import Location, PayloadType, Task
from amr_sim_time_utils import SimulationClock
from amr_generation_provenance import RuleTrace
from amr_staff_policy import resolve_staff_requirement

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SCHEDULED_MODES = {"scheduled", "scheduled_threshold", "scheduled_sporadic"}
THRESHOLD_MODES = {"threshold", "hybrid", "scheduled_threshold"}
CONTINUOUS_MODES = {"continuous", "hybrid", "threshold", "scheduled_threshold"}
SPORADIC_MODES = {"sporadic", "hybrid", "scheduled_sporadic"}
TIMEFRAME_MODES = {"timeframe"}


def _whole_event_count(value: float) -> int:
    """Ignore arithmetic noise within 1e-10 of a whole accumulated event."""
    nearest = round(value)
    return max(0, nearest if math.isclose(value, nearest, rel_tol=0, abs_tol=1e-10) else int(value))


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
    deferred: bool = False
    released_from_deferral: bool = False
    rule_id: str = ""
    rule_path: str = ""


class BaseTaskGenerator:
    """Base class for runtime task generators."""

    generator_type = "base"

    def update_until(self, now: float) -> List[GeneratedTaskRecord]:
        return []

    def scheduled_wake_times(self, horizon: float) -> List[float]:
        return []

    def update_schedules_until(self, now: float) -> List[GeneratedTaskRecord]:
        return []

    def task_state_changed(
        self, task: Task, state: str, event_time: Optional[float] = None
    ) -> List[GeneratedTaskRecord]:
        """Receive completion/failure notifications for generated tasks."""
        return []


def _waste_balance_row(group, generator_type, accrued, residual, collections):
    """One conserved pool; restored attempts are diagnostic, never extra stock."""
    def total(status):
        return sum(item['volume_m3'] for item in collections if item['status'] == status)
    row = {'group': group, 'generator_type': generator_type, 'accrued_m3': accrued,
           'residual_m3': residual, 'pending_m3': total('pending'),
           'completed_m3': total('completed'), 'unconfirmed_m3': total('unconfirmed'),
           'restored_after_failure_m3': total('restored'),
           'collections': [dict(item) for item in collections]}
    row['difference_m3'] = accrued - sum(row[field] for field in
        ('residual_m3', 'pending_m3', 'completed_m3', 'unconfirmed_m3'))
    return row


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


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled", "disable"}:
        return False
    return bool(default)


def _task_id_component(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(value).upper()).strip("_")


def _instance_requires_staff(instance: dict) -> bool:
    cfg = instance.get("cfg", {}) or {}
    requirement = _as_bool(cfg["requires_staff"], False) if "requires_staff" in cfg else None
    return resolve_staff_requirement(
        requirement,
        labels=[instance.get("category_key", ""), instance.get("department_id", "")],
        task_id=f"GEN_{_task_id_component(instance.get('category_key', ''))}_",
        source=cfg.get("task_source", "task_generation"), payload=cfg.get("payload", ""),
    )


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


def _timeframe_minutes_from_cfg(cfg: dict) -> Tuple[Optional[int], Optional[int]]:
    start = _parse_hhmm_to_minutes(cfg.get("timeframe_start"), None)
    end = _parse_hhmm_to_minutes(cfg.get("timeframe_end"), None)
    return start, end


def _normalise_staff_shift_pattern(value: str) -> str:
    pattern = _clean_text(value).lower()
    if pattern in {
        "4_on_4_off_12h",
        "four_on_four_off",
        "four_on_four_off_12_hour",
    }:
        pattern = "four_on_four_off_12h"
    return pattern if pattern in {"none", "four_on_four_off_12h"} else "none"


def _normalise_global_staff_config(value: Optional[dict]) -> dict:
    source = value if isinstance(value, dict) else {}
    patterns = source.get("shift_patterns", {})
    if not isinstance(patterns, dict):
        patterns = {}

    defaults = {
        "none": {
            "display_name": "Fixed working hours",
            "start_time": "09:00",
            "end_time": "17:00",
            "days_active": ["mon", "tue", "wed", "thu", "fri"],
            "work_days": 0,
            "rest_days": 0,
        },
        "four_on_four_off_12h": {
            "display_name": "4 on / 4 off, 12-hour days",
            "start_time": "07:00",
            "end_time": "19:00",
            "days_active": DAY_KEYS,
            "work_days": 4,
            "rest_days": 4,
        },
    }

    clean_patterns: Dict[str, dict] = {}
    for pattern_key, fallback in defaults.items():
        incoming = patterns.get(pattern_key, {})
        incoming = incoming if isinstance(incoming, dict) else {}
        start_time = _clean_text(incoming.get("start_time", fallback["start_time"]))
        end_time = _clean_text(incoming.get("end_time", fallback["end_time"]))
        if _parse_hhmm_to_minutes(start_time, None) is None:
            start_time = fallback["start_time"]
        if _parse_hhmm_to_minutes(end_time, None) is None:
            end_time = fallback["end_time"]
        days = incoming.get("days_active", fallback["days_active"])
        if isinstance(days, str):
            days = [x.strip() for x in days.split(",")]
        clean_days = []
        for day in days or []:
            day_key = _clean_text(day).lower()[:3]
            if day_key in DAY_KEYS and day_key not in clean_days:
                clean_days.append(day_key)
        clean_patterns[pattern_key] = {
            "display_name": _clean_text(
                incoming.get("display_name", fallback["display_name"])
            )
            or fallback["display_name"],
            "start_time": start_time,
            "end_time": end_time,
            "days_active": clean_days or list(fallback["days_active"]),
            "work_days": max(
                0,
                _as_int(
                    incoming.get("work_days", fallback["work_days"]),
                    fallback["work_days"],
                ),
            ),
            "rest_days": max(
                0,
                _as_int(
                    incoming.get("rest_days", fallback["rest_days"]),
                    fallback["rest_days"],
                ),
            ),
        }

    return {
        "enabled": _as_bool(source.get("enabled", True), True),
        "spread_timeframe_tasks": _as_bool(
            source.get(
                "spread_timeframe_tasks",
                source.get("space_timeframe_tasks", True),
            ),
            True,
        ),
        "walking_speed_m_per_sec": max(
            0.1, _as_float(source.get("walking_speed_m_per_sec", 1.2), 1.2)
        ),
        "lift_wait_seconds": max(
            0.0, _as_float(source.get("lift_wait_seconds", 30.0), 30.0)
        ),
        "default_handling_minutes": max(
            0.0, _as_float(source.get("default_handling_minutes", 15.0), 15.0)
        ),
        "amr_hold_for_exchange_max_minutes": max(
            0.0,
            _as_float(
                source.get("amr_hold_for_exchange_max_minutes", 20.0), 20.0
            ),
        ),
        "shift_patterns": clean_patterns,
    }


def _normalise_staff_weekly_hours(value) -> Dict[str, dict]:
    source = value if isinstance(value, dict) else {}
    clean: Dict[str, dict] = {}
    for day_key in DAY_KEYS:
        raw = source.get(day_key, {})
        raw = raw if isinstance(raw, dict) else {}
        enabled = _as_bool(raw.get("enabled", False), False)
        start_time = _clean_text(raw.get("start_time", "09:00")) or "09:00"
        end_time = _clean_text(raw.get("end_time", "17:00")) or "17:00"
        if _parse_hhmm_to_minutes(start_time, None) is None:
            start_time = "09:00"
        if _parse_hhmm_to_minutes(end_time, None) is None:
            end_time = "17:00"
        clean[day_key] = {
            "enabled": enabled,
            "start_time": start_time,
            "end_time": end_time,
        }
    return clean


def _day_key_for_datetime(value: datetime) -> str:
    return DAY_KEYS[value.weekday()]


def _datetime_for_day_and_hhmm(day_start: datetime, hhmm: str) -> datetime:
    hour, minute = [int(x) for x in hhmm.split(":")[:2]]
    return datetime.combine(day_start.date(), dt_time(hour=hour, minute=minute))


def _parse_hhmm_to_minutes(value, default: Optional[int] = None) -> Optional[int]:
    text = _clean_text(value)
    if not text:
        return default
    try:
        parts = text.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if hour == 24 and minute == 0:
            return 24 * 60
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour * 60) + minute
    except Exception:
        return default
    return default


def _minutes_to_time(value: int) -> dt_time:
    value = max(0, min(int(value), 24 * 60))
    if value >= 24 * 60:
        return dt_time(hour=23, minute=59, second=59)
    return dt_time(hour=value // 60, minute=value % 60)


def _department_operating_start_minutes(dept: dict) -> int:
    from amr_generation_inputs import department_schedule_minutes
    return department_schedule_minutes(dept)[0]


def _department_operating_end_minutes(dept: dict) -> int:
    from amr_generation_inputs import department_schedule_minutes
    return department_schedule_minutes(dept)[1]


def _department_operating_hours_per_day(dept: dict) -> float:
    from amr_generation_inputs import department_schedule_minutes
    start, end = department_schedule_minutes(dept)
    return (end - start) / 60.0


def _department_operating_periods_for_date(
    dept: dict, day: datetime
) -> List[Tuple[datetime, datetime]]:
    if not bool(dept.get("enabled", True)):
        return []

    active_days = dept.get("days_active", []) or []
    if active_days:
        allowed = {_clean_text(x).lower() for x in active_days if _clean_text(x)}
        if _day_key_for_datetime(day) not in allowed:
            return []

    start_min = _department_operating_start_minutes(dept)
    end_min = _department_operating_end_minutes(dept)
    if end_min <= start_min:
        end_min += 24 * 60

    duration_min = max(0, end_min - start_min)
    if duration_min <= 0:
        return []

    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    start_dt = day_start + timedelta(minutes=start_min)
    end_dt = day_start + timedelta(minutes=end_min)
    return [(start_dt, end_dt)]


def _department_is_open_at_datetime(dept: Optional[dict], value: datetime) -> bool:
    if not dept:
        return True
    for offset in (-1, 0):
        base_day = (value + timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for start_dt, end_dt in _department_operating_periods_for_date(dept, base_day):
            if start_dt <= value < end_dt:
                return True
    return False


def _department_active_seconds_between(
    dept: Optional[dict], start_dt: datetime, end_dt: datetime
) -> float:
    if not dept:
        return max(0.0, (end_dt - start_dt).total_seconds())
    if end_dt <= start_dt:
        return 0.0

    total = 0.0
    cursor_day = (start_dt - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    final_day = end_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    while cursor_day <= final_day:
        for period_start, period_end in _department_operating_periods_for_date(
            dept, cursor_day
        ):
            overlap_start = max(start_dt, period_start)
            overlap_end = min(end_dt, period_end)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds()
        cursor_day += timedelta(days=1)
    return total


def _next_department_open_datetime(
    dept: Optional[dict], value: datetime
) -> Optional[datetime]:
    if not dept:
        return value
    if _department_is_open_at_datetime(dept, value):
        return value

    cursor_day = (value - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for _ in range(16):
        for start_dt, end_dt in _department_operating_periods_for_date(
            dept, cursor_day
        ):
            if value < start_dt:
                return start_dt
            if start_dt <= value < end_dt:
                return value
        cursor_day += timedelta(days=1)
    return None


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
        waste_stream_paths: Optional[Dict[str, str]] = None,
        prepare_runtime: bool = True,
    ):
        self.task_generation = task_generation or {}
        self.staff_config = _normalise_global_staff_config(
            self.task_generation.get(
                "staff_config", self.task_generation.get("staff", {})
            )
        )
        self.departments = list(departments or [])
        self.locations = locations or {}
        self.payloads = payloads or {}
        self.clock = clock
        self.waste_streams = waste_streams or {}
        self.waste_stream_paths = waste_stream_paths or {}
        self.task_counter = 0
        self.return_counter = 0
        self.scheduled_emitted = set()
        self.runtime: Dict[str, dict] = {}
        self.item_runtime: Dict[str, dict] = {}
        self.direct_volume_requests: Dict[str, dict] = {}
        self.release_spacing_active: Dict[str, str] = {}
        self.deferred_release_queues: Dict[str, List[GeneratedTaskRecord]] = {}
        self.instances = self._build_instances()
        # Definition checks must not expand potentially huge requested task
        # counts. Only runtime/preview generation needs these schedule caches.
        if prepare_runtime:
            self._prepare_instance_runtime_fields()
        self._timeframe_group_members = self._build_timeframe_group_members() if prepare_runtime else {}
        self._timeframe_allocation_cache: Dict[tuple, Tuple[int, int]] = {}
        self._schedule_calendars: Dict[str, dict] = {}

    def _next_task_id(self, category_key: str, department_id: str = "") -> str:
        self.task_counter += 1
        safe_cat = _task_id_component(category_key)
        safe_dept = _task_id_component(department_id)
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
        if not _as_bool(cfg.get("enabled", False), False):
            return False
        active_days = cfg.get("days_active", []) or []
        if active_days:
            allowed = {_clean_text(x).lower() for x in active_days if _clean_text(x)}
            if self._day_key_for_sim_time(sim_time_sec) not in allowed:
                return False

        # Optional fortnightly recurrence. Week 0 starts at the simulation
        # start date, so checked tasks run in the first week, skip the next,
        # then repeat every other week. This applies to all dynamic category
        # generation modes because _category_is_active gates scheduled,
        # threshold, continuous, sporadic and tracked-item generation.
        if _as_bool(cfg.get("run_every_fortnight", False), False):
            current_day = self.clock.sim_seconds_to_datetime(sim_time_sec).date()
            start_day = self.clock.start_datetime.date()
            week_index = max(0, (current_day - start_day).days // 7)
            if week_index % 2 != 0:
                return False

        return True

    def _instance_department(self, instance: dict) -> Optional[dict]:
        dept = instance.get("department")
        return dept if isinstance(dept, dict) else None

    def _instance_is_active(self, instance: dict, sim_time_sec: float) -> bool:
        cfg = instance.get("cfg", {}) or {}
        if not self._category_is_active(cfg, sim_time_sec):
            return False
        dept = self._instance_department(instance)
        if dept is not None:
            return _department_is_open_at_datetime(
                dept, self.clock.sim_seconds_to_datetime(sim_time_sec)
            )
        return True

    def _instance_active_elapsed_seconds(
        self, instance: dict, start_sec: float, end_sec: float
    ) -> float:
        dept = self._instance_department(instance)
        return _department_active_seconds_between(
            dept,
            self.clock.sim_seconds_to_datetime(start_sec),
            self.clock.sim_seconds_to_datetime(end_sec),
        )

    def _generation_active_elapsed_seconds(self, instance: dict, start_sec: float, end_sec: float) -> float:
        """Integrate category eligibility and department opening over the interval."""
        cursor = self.clock.sim_seconds_to_datetime(start_sec)
        end = self.clock.sim_seconds_to_datetime(end_sec)
        total = 0.0
        while cursor < end:
            boundary = min(end, cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
            if self._category_is_active(instance['cfg'], (cursor - self.clock.start_datetime).total_seconds()):
                total += _department_active_seconds_between(self._instance_department(instance), cursor, boundary)
            cursor = boundary
        return total

    def _adjust_release_to_department_open(
        self, instance: dict, release_time: float
    ) -> Optional[float]:
        dept = self._instance_department(instance)
        if dept is None:
            return release_time
        release_dt = self.clock.sim_seconds_to_datetime(release_time)
        adjusted = _next_department_open_datetime(dept, release_dt)
        if adjusted is None:
            return None
        return (adjusted - self.clock.start_datetime).total_seconds()

    def _day_key_for_sim_time(self, sim_time_sec: float) -> str:
        return _day_key_for_datetime(self.clock.sim_seconds_to_datetime(sim_time_sec))

    def _merge_category_with_override(
        self, category: dict, override: Optional[dict], trace=None
    ) -> dict:
        merged = dict(category or {})
        merged.pop("departments", None)
        if isinstance(override, dict):
            merged.update(override)
        if trace is not None:
            for key, value in (category or {}).items():
                trace.record(key, value, 'Category default')
            for key, value in (override or {}).items():
                trace.record(key, value, 'Override')
        # Zone capacity is an operating rule for the payload category, not an
        # individual department. Old projects may still contain stale values in
        # department overrides; deliberately restore the category-wide value.
        merged["dropoff_zone_capacity_policy"] = str(
            (category or {}).get(
                "dropoff_zone_capacity_policy", "allow_temporary_overflow"
            )
            or "allow_temporary_overflow"
        ).strip().lower()
        if trace is not None:
            trace.record('dropoff_zone_capacity_policy', merged['dropoff_zone_capacity_policy'],
                         'Category-wide policy' if 'dropoff_zone_capacity_policy' in (category or {}) else 'Generator default',
                         'Category policy is restored after the ordinary group/department override; blank defaults to allow_temporary_overflow, then whitespace and case are normalised.')
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

    def _department_dropoff_zone_locations(
        self, dept: dict, category_key: str
    ) -> List[str]:
        """Return AMR staging zones associated with a department/category.

        Department category locations remain the human-facing final destinations.
        The optional zone list uses the same association structure but redirects
        the AMR leg to an intermediate location.
        """
        category_locations = dept.get("task_generation_locations", {}) or {}
        entry = category_locations.get(category_key, {}) or {}
        if not isinstance(entry, dict):
            return []
        values = entry.get(
            "dropoff_zone_locations", entry.get("drop_off_zone_locations", [])
        )
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

    def _grouped_department_overrides(self, category: dict) -> tuple[List[dict], set]:
        groups = (
            category.get("department_groups", [])
            if isinstance(category.get("department_groups", []), list)
            else []
        )
        grouped: List[dict] = []
        covered_departments = set()
        seen_ids = set()

        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue

            payload = group.get("payload", {})
            departments = [
                _clean_text(x) for x in group.get("departments", []) if _clean_text(x)
            ]
            if not isinstance(payload, dict) or not departments:
                continue

            group_id = _clean_text(group.get("id", "")) or f"group_{index + 1}"
            if group_id in seen_ids:
                group_id = f"{group_id}_{index + 1}"
            seen_ids.add(group_id)
            covered_departments.update(departments)
            grouped.append(
                {
                    "id": group_id,
                    "source_index": index,
                    "departments": departments,
                    "payload": dict(payload),
                }
            )

        return grouped, covered_departments

    def _append_department_instance(
        self,
        instances: List[dict],
        category_key_text: str,
        category: dict,
        dept: dict,
        override: dict,
        instance_suffix: str = "",
    ) -> None:
        dept_id = self._department_id(dept)
        if not dept_id:
            return

        trace = RuleTrace()
        cfg = self._merge_category_with_override(category, override, trace)
        if not bool(cfg.get("enabled", False)):
            return

        dept_locations = self._department_category_locations(dept, category_key_text)
        dropoff_zone_locations = self._department_dropoff_zone_locations(
            dept, category_key_text
        )
        role = _clean_text(cfg.get("department_location_role", "dropoff")) or "dropoff"

        pickup_locations = self._pickup_locations_from_cfg(cfg)
        dropoff_locations = self._dropoff_locations_from_cfg(cfg)

        if role == "pickup" and dept_locations:
            pickup_locations = dept_locations
        elif role != "pickup" and dept_locations:
            if dropoff_zone_locations:
                # The AMR stages at the zone. A department person completes the
                # final leg and returns the configured empty/equivalent payload.
                dropoff_locations = dropoff_zone_locations
                cfg["requires_staff"] = True
                cfg["return_enabled"] = True
                for key in ('requires_staff', 'return_enabled'):
                    trace.record(key, True, 'Department drop-off zone handoff',
                                 'A department destination with a drop-off zone requires staff handoff and return.')
            else:
                dropoff_locations = dept_locations
        department_location_role = role if dept_locations else ""

        suffix = _clean_text(instance_suffix)
        key_base = f"{category_key_text}:{dept_id}"
        instance_key = f"{key_base}:{suffix}" if suffix else key_base

        if category_key_text.lower() == "waste":
            stream_items = self._department_waste_stream_items(dept)

            if stream_items:
                for stream_item in stream_items:
                    stream_trace = RuleTrace()
                    stream_cfg = self._waste_stream_cfg_for_department(
                        category, override, stream_item, stream_trace
                    )
                    if not stream_cfg:
                        continue
                    stream_name = _clean_text(stream_cfg.get("waste_stream"))
                    container_group = self._waste_container_group_for_instance(
                        dept_id, stream_name, stream_cfg, pickup_locations
                    )
                    stream_cfg["container_group"] = container_group
                    stream_trace.record('container_group', container_group, 'Derived container group',
                                        'Explicit shared group, otherwise shared pickup/stream signature, otherwise department/stream identity.')
                    unique_key = f"waste:{dept_id}:{stream_name}"
                    if suffix:
                        unique_key = f"{unique_key}:{suffix}"
                    instances.append(
                        {
                            "key": unique_key,
                            "volume_key": container_group,
                            "schedule_key": unique_key,
                            "category_key": "waste",
                            "department_id": dept_id,
                            "department_name": self._department_name(dept),
                            "department": dict(dept),
                            "cfg": stream_cfg,
                            '_rule_trace': stream_trace,
                            '_source_department': dept,
                            "pickup_locations": pickup_locations,
                            "dropoff_locations": dropoff_locations,
                            "waste_stream": stream_name,
                            "container_group": container_group,
                        }
                    )
                return

            # Backwards compatibility: if no department streams are set,
            # use the old department waste category override.

        instances.append(
            {
                "key": instance_key,
                "category_key": category_key_text,
                "department_id": dept_id,
                "department_name": self._department_name(dept),
                "department": dict(dept),
                "cfg": cfg,
                '_rule_trace': trace,
                "pickup_locations": pickup_locations,
                "dropoff_locations": dropoff_locations,
                "final_destination_locations": (
                    dept_locations if role != "pickup" and dropoff_zone_locations else []
                ),
                "dropoff_zone_locations": (
                    dropoff_zone_locations if role != "pickup" else []
                ),
                "department_location_role": department_location_role,
            }
        )

    def _threshold_from_waste_stream(self, stream_name: str, cfg: dict) -> float:
        threshold = _as_float(cfg.get("threshold_volume_m3", 0.0), 0.0)
        if threshold > 0:
            return threshold

        stream_cfg = self.waste_streams.get(stream_name, {}) or {}
        capacity = _as_float(cfg.get("container_capacity_m3", stream_cfg.get("container_capacity_m3", 0.0)), 0.0)
        fraction = _as_float(cfg.get("full_threshold_fraction", stream_cfg.get("full_threshold_fraction", 0.8)), 0.8)
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
        self, category_cfg: dict, dept_override: dict, stream_item: dict, trace=None
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

        cfg = self._merge_category_with_override(category_cfg, dept_override, trace)

        # Global stream definition supplies the container/payload defaults.
        for key in ("payload", "container_capacity_m3", "full_threshold_fraction"):
            if key in global_stream and _clean_text(global_stream.get(key)):
                cfg[key] = global_stream.get(key)
                if trace is not None:
                    trace.record(key, cfg[key], 'Waste stream default')

        # The department's selected stream item supplies generation settings and
        # may intentionally override the global stream payload if present.
        for key, value in stream_item.items():
            if key == "name":
                continue
            cfg[key] = value
            if trace is not None:
                trace.record(key, value, 'Department waste stream')

        cfg["waste_stream"] = stream_name
        cfg["task_source"] = "department_waste"
        cfg["initial_container_present"] = bool(
            cfg.get("initial_container_present", True)
        )
        cfg["shared_container"] = bool(cfg.get("shared_container", False))
        cfg["shared_container_group"] = _clean_text(
            cfg.get("shared_container_group", cfg.get("shared_container_id", ""))
        )
        if trace is not None:
            trace.record('waste_stream', stream_name, 'Derived stream identity', 'Name of the selected department waste stream.')
            trace.record('task_source', cfg['task_source'], 'Generator default', 'Department stream instances use department_waste.')
            for key in ('initial_container_present', 'shared_container', 'shared_container_group'):
                trace.record(key, cfg[key], 'Normalised waste setting',
                             'Boolean defaults: initial container present true, shared container false. Shared group uses shared_container_group, then shared_container_id; text is trimmed.')

        payload_name = _clean_text(cfg.get("payload", ""))
        if not payload_name:
            payload_name = _clean_text(global_stream.get("payload", ""))
            cfg["payload"] = payload_name
            if trace is not None:
                trace.record('payload', payload_name, 'Waste stream default', 'Blank effective payload falls back to the global stream payload.')

        if payload_name not in self.payloads:
            return None

        threshold = self._threshold_from_waste_stream(stream_name, cfg)
        if threshold > 0:
            threshold_basis = (
                f"Positive effective threshold {cfg.get('threshold_volume_m3')} m³ is retained and converted to a number."
                if _as_float(cfg.get('threshold_volume_m3', 0.0), 0.0) > 0 else
                f"Effective capacity {_as_float(cfg.get('container_capacity_m3', 0.0), 0.0)} m³ × "
                f"effective fraction {_as_float(cfg.get('full_threshold_fraction', 0.8), 0.8)} = {threshold} m³. "
                'Uses resolved values after department stream overrides.')
            cfg["threshold_volume_m3"] = threshold
            if trace is not None:
                trace.record('threshold_volume_m3', threshold, 'Derived threshold',
                             threshold_basis)

        if _as_float(cfg.get("volume_per_event_m3", 0.0), 0.0) <= 0.0:
            cfg["volume_per_event_m3"] = threshold
            if trace is not None:
                trace.record('volume_per_event_m3', threshold, 'Derived event volume',
                             'Non-positive or absent event volume uses the resolved threshold, including zero.')

        return cfg

    def _build_instances(self) -> List[dict]:
        categories = self.task_generation.get("categories", {}) or {}
        instances: List[dict] = []

        def annotate(rows, category, category_path, override=None, override_path=''):
            for instance in rows:
                instance['rule_path'] = override_path or category_path
                instance['category_path'] = category_path
                origins = {'Category default': category_path, 'Category-wide policy': category_path}
                if override_path:
                    origins['Override'] = override_path
                if instance.get('waste_stream'):
                    # Input arrays retain source ordering. Duplicate global stream
                    # names use the last definition; department streams use first.
                    stream = instance['waste_stream']
                    if stream in self.waste_stream_paths:
                        origins['Waste stream default'] = self.waste_stream_paths[stream]
                    dept_index = next((i for i, dept in enumerate(self.departments)
                                       if dept is instance.get('_source_department')), None)
                    if dept_index is not None:
                        raw = self.departments[dept_index].get('waste_streams', [])
                        stream_index = next((i for i, item in enumerate(raw)
                            if _clean_text(item.get('name') if isinstance(item, dict) else item) == stream), None)
                        if stream_index is not None and isinstance(raw[stream_index], dict):
                            origins['Department waste stream'] = f'/departments/{dept_index}/waste_streams/{stream_index}'
                trace = instance.pop('_rule_trace')
                instance.pop('_source_department', None)
                instance['field_provenance'] = trace.resolve(instance['cfg'], origins,
                    {'Override': 'Group override' if '/department_groups/' in override_path else 'Department override'})
                instance['field_sources'] = {key: (entry['path'] + (' (category-wide policy)' if entry['source'] == 'Category-wide policy' else '')
                                                  if entry['path'] else entry['source'])
                                             for key, entry in instance['field_provenance'].items()}

        for category_key, category in categories.items():
            if not isinstance(category, dict):
                continue

            category_key_text = str(category_key)
            category_path = '/task_generation/categories/' + category_key_text.replace('~', '~0').replace('/', '~1')
            overrides = (
                category.get("departments", {})
                if isinstance(category.get("departments", {}), dict)
                else {}
            )
            groups, grouped_department_ids = self._grouped_department_overrides(
                category
            )
            departments_by_id = {
                self._department_id(dept): dept
                for dept in self.departments
                if self._department_id(dept)
            }

            # Department overrides are independently enabled.  The category
            # default "enabled" flag must not disable configured departments.
            # Waste is the only category that expands into one instance per
            # configured department waste stream.
            for group in groups:
                for dept_id in group["departments"]:
                    dept = departments_by_id.get(dept_id)
                    if dept is None:
                        continue
                    before = len(instances)
                    self._append_department_instance(
                        instances,
                        category_key_text,
                        category,
                        dept,
                        group["payload"],
                        f"group:{group['id']}",
                    )
                    annotate(instances[before:], category, category_path, group['payload'],
                             f"{category_path}/department_groups/{group['source_index']}/payload")

            for dept in self.departments:
                dept_id = self._department_id(dept)
                if not dept_id or dept_id not in overrides:
                    continue
                if dept_id in grouped_department_ids:
                    continue
                before = len(instances)
                self._append_department_instance(
                    instances,
                    category_key_text,
                    category,
                    dept,
                    overrides.get(dept_id, {}),
                )
                annotate(instances[before:], category, category_path, overrides.get(dept_id, {}),
                         category_path + '/departments/' + dept_id.replace('~', '~0').replace('/', '~1'))

            # Category-level generation is only for a deliberately enabled
            # category default and only when there are no department overrides.
            # This prevents the "Category defaults" row from creating a site-wide
            # task in addition to department-level tasks.
            if bool(category.get("enabled", False)) and not overrides and not groups:
                trace = RuleTrace()
                instances.append(
                    {
                        "key": category_key_text,
                        "category_key": category_key_text,
                        "department_id": "",
                        "department_name": "",
                        "cfg": self._merge_category_with_override(category, None, trace),
                        '_rule_trace': trace,
                        "pickup_locations": self._pickup_locations_from_cfg(category),
                        "dropoff_locations": self._dropoff_locations_from_cfg(category),
                    }
                )
                annotate(instances[-1:], category, category_path)

        return instances

    def _prepare_instance_runtime_fields(self) -> None:
        """Cache config-derived values used repeatedly during generation."""
        for instance in self.instances:
            cfg = instance.get("cfg", {}) or {}
            weekly_hours = _normalise_staff_weekly_hours(
                cfg.get("staff_working_hours", {})
            )
            weekly_key = tuple(
                (
                    day_key,
                    bool(weekly_hours[day_key].get("enabled", False)),
                    _clean_text(weekly_hours[day_key].get("start_time", "")),
                    _clean_text(weekly_hours[day_key].get("end_time", "")),
                )
                for day_key in DAY_KEYS
            )
            generation_mode = (
                _clean_text(cfg.get("generation_mode", "scheduled")) or "scheduled"
            )
            payload_name = _clean_text(cfg.get("payload", ""))
            active_days = tuple(
                _clean_text(x).lower()[:3]
                for x in (cfg.get("days_active", []) or [])
                if _clean_text(x)
            )

            instance["_timeframe_group_key"] = (
                _clean_text(instance.get("category_key", "")).lower(),
                _clean_text(cfg.get("staff_resource_name", "")).lower(),
                self._staff_shift_definition(cfg)[0],
                bool(
                    _as_bool(cfg.get("staff_use_custom_working_hours", False), False)
                ),
                bool(
                    _as_bool(
                        cfg.get("staff_department_fallback_enabled", False), False
                    )
                ),
                weekly_key,
                _clean_text(cfg.get("timeframe_start", "")),
                _clean_text(cfg.get("timeframe_end", "")),
            )
            instance["_generation_mode"] = generation_mode
            instance["_requires_staff"] = _instance_requires_staff(instance)
            instance["_payload_name"] = payload_name
            instance["_enabled"] = _as_bool(cfg.get("enabled", False), False)
            instance["_active_days"] = active_days
            instance["_run_every_fortnight"] = _as_bool(
                cfg.get("run_every_fortnight", False), False
            )
            instance["_timeframe_task_count"] = (
                self._calculate_timeframe_instance_task_count(instance, payload_name)
            )

    def _build_timeframe_group_members(self) -> Dict[tuple, List[dict]]:
        groups: Dict[tuple, List[dict]] = {}
        for instance in self.instances:
            if instance.get("_generation_mode") not in TIMEFRAME_MODES:
                continue
            if not bool(instance.get("_requires_staff", False)):
                continue
            group_key = self._timeframe_group_key(instance)
            groups.setdefault(group_key, []).append(instance)

        for members in groups.values():
            members.sort(key=lambda item: str(item.get("key", "")))
        return groups

    def _valid_locations_and_payload(
        self, pickup: str, dropoff: str, payload: str
    ) -> bool:
        return bool(
            pickup in self.locations
            and dropoff in self.locations
            and payload in self.payloads
        )

    def _timeframe_group_key(self, instance: dict) -> tuple:
        cached = instance.get("_timeframe_group_key")
        if cached is not None:
            return cached
        cfg = instance.get("cfg", {}) or {}
        weekly_hours = _normalise_staff_weekly_hours(
            cfg.get("staff_working_hours", {})
        )
        weekly_key = tuple(
            (
                day_key,
                bool(weekly_hours[day_key].get("enabled", False)),
                _clean_text(weekly_hours[day_key].get("start_time", "")),
                _clean_text(weekly_hours[day_key].get("end_time", "")),
            )
            for day_key in DAY_KEYS
        )
        return (
            _clean_text(instance.get("category_key", "")).lower(),
            _clean_text(cfg.get("staff_resource_name", "")).lower(),
            self._staff_shift_definition(cfg)[0],
            bool(_as_bool(cfg.get("staff_use_custom_working_hours", False), False)),
            bool(
                _as_bool(cfg.get("staff_department_fallback_enabled", False), False)
            ),
            weekly_key,
            _clean_text(cfg.get("timeframe_start", "")),
            _clean_text(cfg.get("timeframe_end", "")),
        )

    def _calculate_timeframe_instance_task_count(
        self, instance: dict, payload_name: Optional[str] = None
    ) -> int:
        cfg = instance.get("cfg", {}) or {}
        multiple = max(
            1,
            _as_int(
                cfg.get("timeframe_payload_multiple", cfg.get("payload_multiple", 1)),
                1,
            ),
        )
        if payload_name is None:
            payload_name = _clean_text(cfg.get("payload", ""))
        return sum(
            1
            for index in range(multiple)
            for pickup, dropoff in self._pick_pairs(instance, index)
            if self._valid_locations_and_payload(pickup, dropoff, payload_name)
        )

    def _timeframe_instance_task_count(self, instance: dict) -> int:
        cached = instance.get("_timeframe_task_count")
        if cached is not None:
            return int(cached)
        return self._calculate_timeframe_instance_task_count(instance)

    def _instance_has_active_timeframe(self, instance: dict, base_day: datetime) -> bool:
        """Pool membership follows eligible release dates, including after midnight.

        Membership reserves ordinal positions, not staff. Individual slots still
        obey active-day/fortnight gates; excluded slots are not redistributed.
        """
        cfg = instance.get("cfg", {}) or {}
        start, end = _timeframe_minutes_from_cfg(cfg)
        if start is None or end is None:
            return False
        if end <= start:
            end += 24 * 60
        periods = self._department_work_periods(
            instance, base_day + timedelta(minutes=start), base_day + timedelta(minutes=end)
        )
        for period_start, period_end in periods:
            cursor = period_start
            while cursor < period_end:
                seconds = (cursor - self.clock.start_datetime).total_seconds()
                if self._category_is_active(cfg, seconds):
                    return True
                cursor = cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return False

    def _timeframe_group_allocation(
        self, instance: dict, base_day: datetime
    ) -> Tuple[int, int]:
        group_key = self._timeframe_group_key(instance)
        date_key = base_day.date().isoformat()
        cache_key = (group_key, date_key, instance.get("key", ""))
        cached = self._timeframe_allocation_cache.get(cache_key)
        if cached is not None:
            return cached

        members = [
            item
            for item in self._timeframe_group_members.get(group_key, [])
            if self._instance_has_active_timeframe(item, base_day)
        ]

        offset = 0
        total = sum(self._timeframe_instance_task_count(item) for item in members)
        total = max(1, total)
        for item in members:
            count = self._timeframe_instance_task_count(item)
            item_cache_key = (group_key, date_key, item.get("key", ""))
            self._timeframe_allocation_cache[item_cache_key] = (offset, total)
            offset += count

        return self._timeframe_allocation_cache.get(cache_key, (0, total))

    def _staff_shift_definition(self, cfg: dict) -> Tuple[str, dict]:
        if not _as_bool(self.staff_config.get("enabled", True), True):
            # Disabling shared patterns leaves staff available without a global
            # calendar or rotating team. Custom weekly hours still take priority.
            return "none", {"start_time": "00:00", "end_time": "24:00",
                            "days_active": DAY_KEYS, "work_days": 0, "rest_days": 0}
        pattern_key = _normalise_staff_shift_pattern(
            cfg.get("staff_shift_pattern", "none")
        )
        patterns = self.staff_config.get("shift_patterns", {}) or {}
        pattern = patterns.get(pattern_key, patterns.get("none", {})) or {}
        return pattern_key, pattern

    def _staff_shift_window_for_day(
        self, cfg: dict, base_day: datetime
    ) -> Optional[Tuple[datetime, datetime]]:
        use_custom_hours = _as_bool(
            cfg.get("staff_use_custom_working_hours", False), False
        )
        if (
            not use_custom_hours
            and not _as_bool(self.staff_config.get("enabled", True), True)
        ):
            return None

        if use_custom_hours:
            weekly_hours = _normalise_staff_weekly_hours(
                cfg.get("staff_working_hours", {})
            )
            day_cfg = weekly_hours.get(_day_key_for_datetime(base_day), {})
            if not _as_bool(day_cfg.get("enabled", False), False):
                return None
            start_minutes = _parse_hhmm_to_minutes(
                day_cfg.get("start_time"), None
            )
            end_minutes = _parse_hhmm_to_minutes(day_cfg.get("end_time"), None)
        else:
            pattern_key, pattern = self._staff_shift_definition(cfg)
            active_days = {
                _clean_text(x).lower()[:3]
                for x in pattern.get("days_active", DAY_KEYS)
                if _clean_text(x)
            }
            if pattern_key != 'four_on_four_off_12h' and active_days and _day_key_for_datetime(base_day) not in active_days:
                return None
            start_minutes = _parse_hhmm_to_minutes(pattern.get("start_time"), None)
            end_minutes = _parse_hhmm_to_minutes(pattern.get("end_time"), None)
        if start_minutes is None or end_minutes is None or start_minutes == end_minutes:
            return None
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60

        day_start = base_day.replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            day_start + timedelta(minutes=start_minutes),
            day_start + timedelta(minutes=end_minutes),
        )

    def _department_work_periods(
        self, instance: dict, start_dt: datetime, end_dt: datetime
    ) -> List[Tuple[datetime, datetime]]:
        dept = self._instance_department(instance)
        if dept is None:
            return [(start_dt, end_dt)]

        candidate_periods: List[Tuple[datetime, datetime]] = []
        cursor = (start_dt - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        final_day = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        while cursor <= final_day:
            candidate_periods.extend(
                _department_operating_periods_for_date(dept, cursor)
            )
            cursor += timedelta(days=1)

        overlaps = []
        for period_start, period_end in candidate_periods:
            overlap_start = max(start_dt, period_start)
            overlap_end = min(end_dt, period_end)
            if overlap_end > overlap_start:
                overlaps.append((overlap_start, overlap_end))
        return overlaps

    def _timeframe_work_periods(
        self,
        instance: dict,
        timeframe_start: datetime,
        timeframe_end: datetime,
    ) -> Tuple[List[Tuple[datetime, datetime]], bool, str]:
        """Available periods, spacing flag and any fallback explanation.

        Search the previous day as well as every day in the timeframe so an
        overnight shift remains available. Merge intersections before spacing;
        elapsed time in a closed gap must not consume a release slot.
        """
        cfg = instance.get("cfg", {}) or {}
        staff_spread_enabled = bool(
            _instance_requires_staff(instance)
            and (_as_bool(self.staff_config.get("enabled", True), True)
                 or _as_bool(cfg.get("staff_use_custom_working_hours", False), False))
            and _as_bool(self.staff_config.get("spread_timeframe_tasks", True), True)
        )
        if not staff_spread_enabled:
            return [(timeframe_start, timeframe_end)], False, ''

        overlaps = []
        has_staff_overlap = False
        cursor = (timeframe_start - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        while cursor < timeframe_end:
            shift_window = self._staff_shift_window_for_day(cfg, cursor)
            cursor += timedelta(days=1)
            if shift_window is None:
                continue
            start = max(timeframe_start, shift_window[0])
            end = min(timeframe_end, shift_window[1])
            if end > start:
                has_staff_overlap = True
                overlaps.extend(self._department_work_periods(instance, start, end))
        if not overlaps:
            reason = ('No staff working period overlaps this timeframe.' if not has_staff_overlap else
                      'Staff hours and department opening hours do not overlap within this timeframe.')
            # Retain configured demand. Runtime handling still observes its own
            # hours; this flag does not authorise out-of-hours staffing.
            return [(timeframe_start, timeframe_end)], False, reason
        merged = []
        for start, end in sorted(overlaps):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged, True, ''

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
            requires_staff=(_as_bool(cfg["requires_staff"], False)
                            if "requires_staff" in cfg else None),
            staff_initial_count=max(1, _as_int(cfg.get("staff_initial_count", 1), 1)),
            staff_resource_name=_clean_text(cfg.get("staff_resource_name", "")),
            staff_category_key=category_key,
            staff_movement_policy=_clean_text(
                cfg.get("staff_movement_policy", "batch_same_location")
            )
            or "batch_same_location",
            staff_shift_pattern=_clean_text(cfg.get("staff_shift_pattern", "none"))
            or "none",
            staff_handling_minutes=max(
                0.0, _as_float(cfg.get("staff_handling_minutes", 0.0), 0.0)
            ),
            staff_handoff_only=_as_bool(
                cfg.get("staff_handoff_only", False), False
            ),
            staff_collection_delay_minutes=max(
                0.0,
                _as_float(cfg.get("staff_collection_delay_minutes", 0.0), 0.0),
            ),
            dropoff_zone_capacity_policy=(
                _clean_text(
                    cfg.get(
                        "dropoff_zone_capacity_policy",
                        "allow_temporary_overflow",
                    )
                ).lower()
                or "allow_temporary_overflow"
            ),
            staff_use_custom_working_hours=_as_bool(
                cfg.get("staff_use_custom_working_hours", False), False
            ),
            staff_working_hours=_normalise_staff_weekly_hours(
                cfg.get("staff_working_hours", {})
            ),
            staff_department_fallback_enabled=_as_bool(
                cfg.get("staff_department_fallback_enabled", False), False
            ),
            staff_department_fallback_resource_name=(
                _clean_text(
                    cfg.get(
                        "staff_department_fallback_resource_name",
                        "Department team",
                    )
                )
                or "Department team"
            ),
            release_next_after_return_pickup=_as_bool(
                cfg.get("release_next_after_return_pickup", False), False
            ),
        )
        resolved_final = _clean_text(
            (instance.get("_resolved_final_destination_by_pair", {}) or {}).get(
                (pickup, dropoff), ""
            )
        )
        if resolved_final and resolved_final in self.locations:
            task.dropoff_zone = dropoff
            task.final_destination = resolved_final
            task.final_destination_candidates = [
                value
                for value in instance.get("final_destination_locations", [])
                if value in self.locations and value != dropoff
            ]
            if resolved_final not in task.final_destination_candidates:
                task.final_destination_candidates.insert(0, resolved_final)
            task.requires_staff = True
            if task.dropoff_zone_capacity_policy not in {
                "wait_for_space",
                "allow_temporary_overflow",
            }:
                task.dropoff_zone_capacity_policy = "allow_temporary_overflow"
        # Carry the effective definition independently of the staff choice.
        # Unspecified legacy Stores tasks acquire staff at runtime; dropping
        # these fields here incorrectly gives them all-day availability. Merely
        # carrying metadata does not enable staff on an explicit false choice.
        pattern_key, pattern = self._staff_shift_definition(cfg)
        task.staff_shift_pattern = pattern_key
        task.staff_shift_start_time = _clean_text(pattern.get("start_time", ""))
        task.staff_shift_end_time = _clean_text(pattern.get("end_time", ""))
        task.staff_shift_days_active = list(pattern.get("days_active", []) or [])
        task.staff_shift_work_days = max(0, _as_int(pattern.get("work_days", 0), 0))
        task.staff_shift_rest_days = max(0, _as_int(pattern.get("rest_days", 0), 0))
        task.staff_timeframe_spacing_enabled = _as_bool(
            self.staff_config.get("spread_timeframe_tasks", True), True
        )
        # Seeded waste bins acquire a mandatory same-instance return at runtime,
        # even when the category has no generic return payload. Keep its timing
        # and routing policy available for that later decision.
        task.return_delay_minutes = _as_float(cfg.get("return_delay_minutes", 0.0), 0.0)
        task.return_route_profile = _clean_text(
            cfg.get("return_route_profile", cfg.get("route_profile", ""))
        )
        task.return_priority = _as_int(cfg.get("return_priority", cfg.get("priority", 100)), 100)
        if bool(cfg.get("return_enabled", False)) or bool(task.dropoff_zone):
            return_payload = _clean_text(cfg.get("return_payload", ""))
            if not return_payload and task.dropoff_zone:
                return_payload = payload_name
            if return_payload in self.payloads:
                task.return_enabled = True
                task.return_payload = return_payload
        if task.release_next_after_return_pickup and task.return_enabled:
            task.generator_release_spacing_key = f"dropoff:{task.dropoff}"
            task.generator_collection_task_id = task.id
            task.generator_scheduled_release_time = float(task.release_time)

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
        if str(getattr(task, "dropoff_zone", "") or "").strip():
            details = (
                f"{details}; AMR drop-off zone={task.dropoff_zone}; "
                f"final destination={task.final_destination}"
            )
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
            rule_id=instance['key'],
            rule_path=instance.get('rule_path', ''),
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
        component = getattr(outbound, 'generator_direct_volume_component', '')
        if component and not getattr(outbound, 'is_return_task', False):
            self.direct_volume_requests.setdefault(outbound.id, {
                'task_id': outbound.id, 'rule_id': instance['key'], 'component': component,
                'volume_m3': outbound.generated_volume_m3, 'status': 'pending',
            })
        if getattr(outbound, 'tracked_item_exchange', False) and not getattr(outbound, 'generator_item_key', ''):
            self._register_scheduled_tracked_request(outbound, instance)
        record = self._record_for_task(
            outbound,
            instance,
            "task_generated",
            reason,
        )
        spacing_key = _clean_text(
            getattr(outbound, "generator_release_spacing_key", "")
        )
        if not spacing_key:
            return [record]

        active_task_id = _clean_text(self.release_spacing_active.get(spacing_key, ""))
        if not active_task_id:
            self.release_spacing_active[spacing_key] = outbound.id
            return [record]

        outbound.generator_deferred_by_task_id = active_task_id
        record.deferred = True
        self.deferred_release_queues.setdefault(spacing_key, []).append(record)
        return [record]

    def _release_next_deferred_record(
        self, spacing_key: str, blocking_return_task_id: str
    ) -> List[GeneratedTaskRecord]:
        spacing_key = _clean_text(spacing_key)
        if not spacing_key:
            return []
        queue = self.deferred_release_queues.get(spacing_key, [])
        if not queue:
            self.release_spacing_active.pop(spacing_key, None)
            self.deferred_release_queues.pop(spacing_key, None)
            return []

        record = queue.pop(0)
        if not queue:
            self.deferred_release_queues.pop(spacing_key, None)
        record.deferred = False
        record.released_from_deferral = True
        record.task.generator_deferred_by_return_task_id = _clean_text(
            blocking_return_task_id
        )
        self.release_spacing_active[spacing_key] = record.task.id
        return [record]

    def _pick_pairs(
        self, instance: dict, occurrence_index: Optional[int] = None
    ) -> List[Tuple[str, str]]:
        pickups = [
            x for x in instance.get("pickup_locations", []) if x in self.locations
        ]
        dropoffs = [
            x for x in instance.get("dropoff_locations", []) if x in self.locations
        ]
        if not pickups or not dropoffs:
            return []
        role = _clean_text(instance.get("department_location_role", ""))
        if occurrence_index is None:
            occurrence_index = max(
                0, int(instance.get("_location_occurrence_index", 0) or 0)
            )
            instance["_location_occurrence_index"] = occurrence_index + 1
        else:
            occurrence_index = max(0, int(occurrence_index or 0))
        final_destinations = [
            x
            for x in instance.get("final_destination_locations", [])
            if x in self.locations
        ]
        resolved_final = ""
        if final_destinations:
            resolved_final = final_destinations[
                occurrence_index % len(final_destinations)
            ]
        if role == "pickup" and len(pickups) > 1:
            pickups = [pickups[occurrence_index % len(pickups)]]
        elif role and role != "pickup" and len(dropoffs) > 1:
            dropoffs = [dropoffs[occurrence_index % len(dropoffs)]]

        pairs: List[Tuple[str, str]] = []
        resolved_by_pair = {}
        for pickup in pickups:
            for dropoff in dropoffs:
                if pickup != dropoff:
                    pairs.append((pickup, dropoff))
                    if resolved_final and resolved_final != dropoff:
                        resolved_by_pair[(pickup, dropoff)] = resolved_final
        instance["_resolved_final_destination_by_pair"] = resolved_by_pair
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
        while (runtime["volume"] >= threshold_volume or
               math.isclose(runtime["volume"], threshold_volume, rel_tol=1e-12, abs_tol=0)):
            pairs = self._pick_pairs(instance)
            if not pairs:
                break
            # This runtime holds one pooled volume. Each threshold funds one
            # collection, not a full-volume copy for every candidate route.
            pair_index = int(runtime.get('threshold_pair_index', 0))
            pickup, dropoff = pairs[pair_index % len(pairs)]
            task = self._base_task(instance, pickup, dropoff, payload_name, release_time, "threshold")
            if task is not None:
                task.generated_volume_m3 = threshold_volume
                task.waste_volume_m3 = threshold_volume
            collection_records = self._records_for_outbound(task, instance, details)
            if not collection_records:
                break  # No represented collection: retain the accumulated demand.
            runtime['threshold_pair_index'] = pair_index + 1
            if self._is_waste_instance(instance):
                task.generator_volume_key = instance.get('volume_key', instance['key'])
                task.generator_collection_task_id = task.id
                task.generator_threshold_volume_m3 = threshold_volume
                runtime.setdefault('volume_collections', {})[task.id] = {
                    'task_id': task.id, 'rule_id': instance['key'], 'volume_m3': threshold_volume,
                    'status': 'pending', 'requested_pickup': pickup, 'requested_dropoff': dropoff,
                }
            runtime["volume"] = max(0.0, runtime["volume"] - threshold_volume)
            records.extend(collection_records)
        return records

    def _accrue_volume(self, instance, runtime, amount):
        runtime['volume'] = _as_float(runtime.get('volume', 0.0)) + amount
        if self._is_waste_instance(instance):
            runtime['accrued_volume_m3'] = runtime.get('accrued_volume_m3', 0.0) + amount

    def waste_volume_balance(self):
        """Accumulated dynamic waste only; ordinary scheduled/sporadic demand is separate."""
        rows = []
        for key, runtime in sorted(self.runtime.items()):
            if 'accrued_volume_m3' not in runtime:
                continue
            collections = list(runtime.get('volume_collections', {}).values())
            rows.append(_waste_balance_row(key, self.generator_type,
                runtime['accrued_volume_m3'], runtime['volume'], collections))
        return rows

    def _timeframe_records(
        self, instance: dict, now: float, *, wake_times: Optional[set] = None,
        base_days: Optional[List[datetime]] = None,
        diagnostics: Optional[set] = None,
        slot_audit: Optional[list] = None,
    ) -> List[GeneratedTaskRecord]:
        """Emit due slots, or collect their times without creating tasks.

        Calendar planning uses the same staff/group allocation arithmetic as
        emission. It must not consume slots, allocate IDs or alter inventories.
        """
        cfg = instance["cfg"]
        mode = _clean_text(cfg.get("generation_mode", "scheduled")) or "scheduled"
        if mode not in TIMEFRAME_MODES:
            return []

        payload_name = _clean_text(cfg.get("payload", ""))
        if payload_name not in self.payloads:
            return []

        start_minutes, end_minutes = _timeframe_minutes_from_cfg(cfg)
        if start_minutes is None or end_minutes is None:
            if diagnostics is not None:
                diagnostics.add('Timeframe start or end is missing or cannot be interpreted.')
            return []
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60

        multiple = max(
            1,
            _as_int(
                cfg.get("timeframe_payload_multiple", cfg.get("payload_multiple", 1)),
                1,
            ),
        )

        current_dt = self.clock.sim_seconds_to_datetime(now)
        day_start = current_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        records: List[GeneratedTaskRecord] = []

        # Also check the previous day because a timeframe or staff shift can cross
        # midnight. Each individual payload is emitted only when its own spaced
        # release time has been reached.
        if base_days is None:
            base_days = [day_start + timedelta(days=offset) for offset in (-1, 0)]
        for base_day in base_days:
            timeframe_start_dt = base_day + timedelta(minutes=start_minutes)
            timeframe_end_dt = base_day + timedelta(minutes=end_minutes)

            work_periods, spread_applied, out_of_hours_reason = (
                self._timeframe_work_periods(
                    instance, timeframe_start_dt, timeframe_end_dt
                )
            )
            work_start_dt, work_end_dt = work_periods[0][0], work_periods[-1][1]
            if work_end_dt <= work_start_dt:
                continue

            effective_deadline_dt = work_end_dt if spread_applied else timeframe_end_dt
            deadline_time = (
                effective_deadline_dt - self.clock.start_datetime
            ).total_seconds()
            if deadline_time < 0 and slot_audit is None:
                continue

            schedule_key_base = (
                instance.get("schedule_key", instance["key"]),
                "timeframe",
                timeframe_start_dt.date().isoformat(),
                _clean_text(cfg.get("timeframe_start", "")),
                _clean_text(cfg.get("timeframe_end", "")),
                _clean_text(cfg.get("staff_shift_pattern", "none")),
                work_start_dt.isoformat(),
                work_end_dt.isoformat(),
            )

            window_seconds = sum((end - start).total_seconds() for start, end in work_periods)
            group_offset, group_total = self._timeframe_group_allocation(
                instance, base_day
            )
            local_ordinal = 0
            for index in range(multiple):
                pairs = self._pick_pairs(instance, index)
                for pickup, dropoff in pairs:
                    if spread_applied:
                        global_ordinal = group_offset + local_ordinal
                        slot_offset = window_seconds * (
                            float(global_ordinal) / float(max(1, group_total))
                        )
                        for period_start, period_end in work_periods:
                            period_seconds = (period_end - period_start).total_seconds()
                            if slot_offset < period_seconds:
                                candidate_release_dt = period_start + timedelta(seconds=slot_offset)
                                break
                            slot_offset -= period_seconds
                        else:
                            # A slot at the final end is outside the half-open window.
                            candidate_release_dt = work_end_dt
                    else:
                        candidate_release_dt = timeframe_start_dt
                    local_ordinal += 1

                    original_release_time = (
                        candidate_release_dt - self.clock.start_datetime
                    ).total_seconds()
                    release_time = self._adjust_release_to_department_open(
                        instance, original_release_time
                    )
                    audit = {'nominal_date': timeframe_start_dt.date().isoformat(),
                             'payload_index': index + 1, 'pickup': pickup, 'dropoff': dropoff,
                             'planned_release_seconds': original_release_time,
                             'release_seconds': release_time, 'deadline_seconds': deadline_time,
                             'disposition': 'eligible'}
                    if (slot_audit is not None and timeframe_start_dt <= current_dt
                            and timeframe_end_dt > self.clock.start_datetime):
                        slot_audit.append(audit)
                    if release_time is None:
                        audit['disposition'] = 'no_department_opening'
                        if diagnostics is not None:
                            diagnostics.add('No department opening was found for a planned release.')
                        continue
                    if release_time < 0 or original_release_time > now:
                        audit['disposition'] = 'outside_preview'
                        if diagnostics is not None:
                            diagnostics.add('Planned release slots fall outside the preview period.')
                        continue
                    if release_time >= deadline_time:
                        audit['disposition'] = 'at_or_after_deadline'
                        if diagnostics is not None:
                            diagnostics.add(
                                'The department opens at or after the timeframe deadline; releases at the deadline are excluded.'
                                if release_time > original_release_time else
                                'A planned release reaches or exceeds the timeframe deadline; releases at the deadline are excluded.')
                        continue
                    if release_time > now:
                        audit['disposition'] = 'outside_preview'
                        if diagnostics is not None:
                            diagnostics.add('The next department opening or eligible release is after the preview period.')
                        continue
                    if not self._instance_is_active(instance, release_time):
                        audit['disposition'] = 'inactive_release_date'
                        if diagnostics is not None:
                            diagnostics.add('Active days, fortnight rules or department availability exclude the planned release date.')
                        continue

                    if not self._valid_locations_and_payload(pickup, dropoff, payload_name):
                        audit['disposition'] = 'invalid_route_or_payload'
                        continue

                    if wake_times is not None:
                        wake_times.add(release_time)
                        continue

                    pair_key = (pickup, dropoff)
                    schedule_key = schedule_key_base + pair_key + (index,)
                    if schedule_key in self.scheduled_emitted:
                        continue

                    task = self._base_task(
                        instance=instance,
                        pickup=pickup,
                        dropoff=dropoff,
                        payload_name=payload_name,
                        release_time=release_time,
                        label_suffix="timeframe",
                    )
                    if task is None:
                        continue

                    self.scheduled_emitted.add(schedule_key)
                    task.target_time = max(0.0, deadline_time - release_time)
                    task.quantity = 1
                    task.timeframe_start = _clean_text(cfg.get("timeframe_start", ""))
                    task.timeframe_end = _clean_text(cfg.get("timeframe_end", ""))
                    task.timeframe_deadline_time = deadline_time
                    task.timeframe_payload_index = index + 1
                    task.timeframe_payload_multiple = multiple
                    task.staff_timeframe_spaced = bool(spread_applied)
                    task.staff_out_of_hours_required = bool(out_of_hours_reason)
                    task.staff_out_of_hours_reason = out_of_hours_reason
                    task.staff_work_periods = [
                        [(start - self.clock.start_datetime).total_seconds(),
                         (end - self.clock.start_datetime).total_seconds()]
                        for start, end in work_periods] if spread_applied else []
                    task.staff_work_window_start = (
                        work_start_dt - self.clock.start_datetime
                    ).total_seconds()
                    task.staff_work_window_end = deadline_time

                    spacing_note = (
                        'spaced across staff/department working periods ' + ', '.join(
                            f"{start.isoformat(timespec='minutes')} to {end.isoformat(timespec='minutes')}"
                            for start, end in work_periods)
                        if spread_applied
                        else (
                            out_of_hours_reason + ' Runtime staff hours still apply; handling may miss the timeframe deadline.'
                            if out_of_hours_reason
                            else "released at timeframe start"
                        )
                    )
                    records.extend(
                        self._records_for_outbound(
                            task,
                            instance,
                            (
                                f"Generated timeframe {instance['category_key']} task "
                                f"{index + 1}/{multiple}; {spacing_note}; due by "
                                f"{effective_deadline_dt.strftime('%H:%M')}"
                            ),
                        )
                    )

        return records

    def _schedule_calendar(self, instance: dict, through: float) -> dict:
        """Resolve nominal days to effective opening times without creating tasks.

        Retaining the nominal date keeps a late-night service alive when its
        department next opens on another day. Cache extension is chronological;
        consumption uses an index, so old days need not be scanned at every tick.
        """
        first_day = self.clock.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        calendar = self._schedule_calendars.setdefault(
            instance['key'], {'next_day': first_day, 'entries': [], 'index': 0})
        final_day = self.clock.sim_seconds_to_datetime(through).replace(
            hour=0, minute=0, second=0, microsecond=0)
        cfg = instance['cfg']
        times = _scheduled_times_from_cfg(cfg)
        extended = False
        while calendar['next_day'] <= final_day:
            day = calendar['next_day']
            calendar['next_day'] += timedelta(days=1)
            for hhmm in times:
                nominal = _datetime_for_day_and_hhmm(day, hhmm)
                release = self._adjust_release_to_department_open(
                    instance, (nominal - self.clock.start_datetime).total_seconds())
                if release is None or release < 0 or not self._instance_is_active(instance, release):
                    continue
                calendar['entries'].append((release, nominal.date().isoformat(), hhmm))
                extended = True
        if extended:
            calendar['entries'].sort()
        return calendar

    def scheduled_wake_times(self, horizon: float) -> List[float]:
        times = set()
        first_day = self.clock.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        final_day = self.clock.sim_seconds_to_datetime(horizon).replace(
            hour=0, minute=0, second=0, microsecond=0)
        for instance in self.instances:
            cfg = instance['cfg']
            mode = _clean_text(cfg.get('generation_mode', 'scheduled')) or 'scheduled'
            if mode in SCHEDULED_MODES and _clean_text(cfg.get('payload', '')) in self.payloads:
                times.update(release for release, _day, _hhmm in
                             self._schedule_calendar(instance, horizon)['entries']
                             if 0 <= release <= horizon)
            elif mode in TIMEFRAME_MODES:
                day = first_day - timedelta(days=1)
                while day <= final_day:
                    self._timeframe_records(instance, horizon, wake_times=times, base_days=[day])
                    day += timedelta(days=1)
        return sorted(times)

    def update_schedules_until(self, now: float) -> List[GeneratedTaskRecord]:
        records = []
        for instance in self.instances:
            records.extend(self._timeframe_records(instance, now))
            records.extend(self._schedule_records(instance, now))
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

        records: List[GeneratedTaskRecord] = []
        calendar = self._schedule_calendar(instance, now)
        while calendar['index'] < len(calendar['entries']):
            release_time, nominal_day, hhmm = calendar['entries'][calendar['index']]
            if release_time > now:
                break
            calendar['index'] += 1
            schedule_key = (
                instance.get("schedule_key", instance["key"]),
                nominal_day,
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
                self._accrue_volume(instance, runtime, max(
                    0.0, _as_float(cfg.get("volume_per_event_m3", 0.0), 0.0)))
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
                    task.generator_direct_volume_component = 'scheduled'
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
        category_active = self._category_is_active(cfg, now)
        department_open = self._instance_department(
            instance
        ) is None or _department_is_open_at_datetime(
            self._instance_department(instance), self.clock.sim_seconds_to_datetime(now)
        )
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

        elapsed_seconds = self._generation_active_elapsed_seconds(
            instance, last_time, now
        )
        elapsed_days = elapsed_seconds / 86400.0
        records: List[GeneratedTaskRecord] = []
        # Integrate the whole elapsed interval before checking release eligibility.
        # A poll at closing must retain demand from the preceding open hours.
        contributors[contributor_key] = now

        if mode in CONTINUOUS_MODES:
            self._accrue_volume(instance, runtime, max(
                0.0, elapsed_days * _as_float(cfg.get("base_daily_volume_m3", 0.0), 0.0)))

        # Threshold modes use discrete events as fill. Hybrid instead dispatches
        # these events below; adding them to the pool as well duplicates demand.
        if mode in THRESHOLD_MODES and mode not in SPORADIC_MODES:
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
                whole_events = _whole_event_count(volume_event_accumulators[contributor_key])
                if whole_events > 0:
                    self._accrue_volume(instance, runtime, whole_events * event_volume)
                    volume_event_accumulators[contributor_key] = max(0.0, volume_event_accumulators[contributor_key] - whole_events)

        if mode in SPORADIC_MODES:
            freq_per_day = max(0.0, _as_float(cfg.get("frequency_per_day", 0.0), 0.0))
            sporadic_accumulators = runtime.setdefault("sporadic_accumulator", {})
            sporadic_accumulators[contributor_key] = _as_float(
                sporadic_accumulators.get(contributor_key, 0.0), 0.0
            ) + (elapsed_days * freq_per_day)
            accrued = runtime.setdefault('sporadic_accrued_events', {})
            accrued[contributor_key] = accrued.get(contributor_key, 0.0) + elapsed_days * freq_per_day
            whole_events = _whole_event_count(sporadic_accumulators[contributor_key]) if category_active and department_open else 0
            for _ in range(whole_events):
                event_records = []
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
                        task.generator_direct_volume_component = 'sporadic'
                    event_records.extend(
                        self._records_for_outbound(
                            task,
                            instance,
                            f"Generated sporadic {instance['category_key']} task",
                        )
                    )
                if not event_records:
                    break  # No represented work: retain this event and later demand.
                sporadic_accumulators[contributor_key] = max(0.0, sporadic_accumulators[contributor_key] - 1)
                emitted = runtime.setdefault('sporadic_emitted_events', {})
                emitted[contributor_key] = emitted.get(contributor_key, 0) + 1
                records.extend(event_records)

        if mode in THRESHOLD_MODES and category_active and department_open:
            records.extend(
                self._threshold_collection_records(
                    instance,
                    now,
                    f"Generated threshold {instance['category_key']} task",
                )
            )

        contributors[contributor_key] = now
        return records

    def direct_volume_balance(self):
        groups = {}
        for request in self.direct_volume_requests.values():
            groups.setdefault((request['rule_id'], request['component']), []).append(request)
        result = []
        for (rule, component), requests in sorted(groups.items()):
            row = {'rule_id': rule, 'component': component,
                   'requested_m3': sum(r['volume_m3'] for r in requests),
                   'requests': [dict(r) for r in requests]}
            for state in ('pending', 'completed', 'failed_before_pickup', 'unconfirmed'):
                row[state + '_m3'] = sum(r['volume_m3'] for r in requests if r['status'] == state)
            row['difference_m3'] = row['requested_m3'] - sum(row[state + '_m3'] for state in
                ('pending', 'completed', 'failed_before_pickup', 'unconfirmed'))
            result.append(row)
        return result

    def _tracked_resource_locations(self, instance):
        locations = [location for location in instance.get('final_destination_locations', [])
                     if location in self.locations]
        if not locations:
            role = _clean_text(instance.get('department_location_role', ''))
            if role and role != 'pickup':
                locations = [location for location in instance.get('dropoff_locations', [])
                             if location in self.locations]
        return _unique_clean(locations) or ['']

    def _register_scheduled_tracked_request(self, task, instance):
        items = _payload_tracked_items(self.payloads.get(_clean_text(instance['cfg'].get('payload'))))
        if not items:
            return
        resources = self._tracked_resource_locations(instance)
        location = _clean_text(getattr(task, 'final_destination', '') or task.dropoff)
        location = location if location in resources else resources[0]
        runtime = self._advance_tracked_stock(instance, task.release_time, resources, items)
        quantities = runtime['resource_quantities'][location]
        mode = _clean_text(getattr(task, 'exchange_mode', 'top_up_only')) or 'top_up_only'
        pending = [request for request in runtime['requests'].values()
                   if request['resource'] == location and request['status'] == 'pending']
        ordered = {}
        for name, item in items.items():
            incoming = sum(request['quantities'].get(name, 0) for request in pending)
            ordered[name] = (item['target_quantity'] if mode == 'full_exchange' else
                0.0 if mode == 'replace_empty' and quantities[name] > 0 else
                max(0.0, item['target_quantity'] - quantities[name] - incoming))
        task.tracked_items = {name: {**item, 'current_quantity': quantities[name],
                                    'delivery_quantity': ordered[name]} for name, item in items.items()}
        task.generator_item_key = instance['key']
        runtime['requests'][task.id] = {'resource': location, 'mode': mode, 'quantities': ordered, 'status': 'pending'}
        runtime['pending_resources'].setdefault(location, set()).add(task.id)

    def _advance_tracked_stock(self, instance, now, resource_locations, items):
        runtime = self.item_runtime.setdefault(instance['key'], {
            'last_update_time': 0.0, 'resource_quantities': {}, 'balances': {},
            'pending_resources': {}, 'requests': {},
        })
        for location in resource_locations:
            quantities = runtime['resource_quantities'].setdefault(location, {})
            balances = runtime['balances'].setdefault(location, {})
            for name, item in items.items():
                quantities.setdefault(name, item['target_quantity'])
                balances.setdefault(name, {'initial': item['target_quantity'], 'consumed': 0.0,
                    'unmet': 0.0, 'delivered': 0.0, 'removed': 0.0})
        last_time = runtime['last_update_time']
        if now <= last_time:
            return runtime
        elapsed_days = self._generation_active_elapsed_seconds(instance, last_time, now) / 86400.0
        for location in resource_locations:
            quantities = runtime['resource_quantities'][location]
            for name, item in items.items():
                requested = max(0.0, item['consumption_per_day']) * elapsed_days / len(resource_locations)
                consumed = min(quantities[name], requested)
                quantities[name] -= consumed
                runtime['balances'][location][name]['consumed'] += consumed
                runtime['balances'][location][name]['unmet'] += requested - consumed
        runtime['last_update_time'] = now
        return runtime

    def tracked_item_balance(self):
        rows = []
        for rule, runtime in sorted(self.item_runtime.items()):
            for location, items in runtime.get('balances', {}).items():
                for name, balance in items.items():
                    remaining = runtime['resource_quantities'][location][name]
                    rows.append({'rule_id': rule, 'location': location, 'item': name,
                                 **balance, 'remaining': remaining,
                                 'difference': balance['initial'] + balance['delivered'] - balance['consumed']
                                               - balance['removed'] - remaining})
        return rows

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

        # A department can hold the same consumable payload in several physical
        # locations (for example, two clean-linen trolleys).  The configured
        # consumption_per_day is department demand, so divide it between those
        # resources and retain an independent stock balance for each one.
        resource_locations = self._tracked_resource_locations(instance)

        runtime = self._advance_tracked_stock(instance, now, resource_locations, items)
        if not self._instance_is_active(instance, now):
            return []
        resource_quantities = runtime['resource_quantities']
        exchange_mode = _clean_text(cfg.get('exchange_mode', 'top_up_only')) or 'top_up_only'
        triggered_by_resource: Dict[str, Dict[str, dict]] = {}
        for location in resource_locations:
            if location in runtime['pending_resources']:
                continue
            quantities = resource_quantities[location]
            triggered: Dict[str, dict] = {}
            for name, item in items.items():
                trigger = 0.0 if exchange_mode == 'replace_empty' else item['trigger_quantity']
                at_trigger = quantities[name] <= trigger or math.isclose(
                    quantities[name], trigger, rel_tol=1e-12, abs_tol=item['target_quantity'] * 1e-12)
                if quantities[name] < item['target_quantity'] and at_trigger:
                    triggered[name] = {
                        **item,
                        "current_quantity": round(quantities[name], 3),
                        "target_quantity": item["target_quantity"],
                        'delivery_quantity': item['target_quantity'] - quantities[name],
                    }
            if triggered:
                if exchange_mode == 'full_exchange':
                    triggered = {name: {**item, 'current_quantity': quantities[name],
                                        'delivery_quantity': item['target_quantity']}
                                 for name, item in items.items()}
                triggered_by_resource[location] = triggered

        if not triggered_by_resource:
            return []

        records: List[GeneratedTaskRecord] = []
        exchange_mode = (
            _clean_text(cfg.get("exchange_mode", "top_up_only")) or "top_up_only"
        )

        final_destinations = list(instance.get("final_destination_locations", []))
        for resource_location, triggered in triggered_by_resource.items():
            occurrence_index = (
                final_destinations.index(resource_location)
                if resource_location in final_destinations
                else resource_locations.index(resource_location)
            )
            for pickup, dropoff in self._pick_pairs(instance, occurrence_index):
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
                    next(iter(source_locations))
                    if len(source_locations) == 1
                    else pickup
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
                task.generator_item_key = instance['key']
                runtime['requests'][task.id] = {'resource': resource_location, 'mode': exchange_mode,
                    'quantities': {name: item['delivery_quantity'] for name, item in triggered.items()},
                    'status': 'pending'}
                runtime['pending_resources'].setdefault(resource_location, set()).add(task.id)
                records.extend(
                    self._records_for_outbound(
                        task,
                        instance,
                        "Generated tracked item exchange for "
                        f"{', '.join(sorted(triggered.keys()))}"
                        + (
                            f" at {resource_location}"
                            if resource_location
                            else ""
                        ),
                    )
                )
                break  # One stock deficit funds one replenishment for this resource.

        return records

    def task_state_changed(
        self, task: Task, state: str, event_time: Optional[float] = None
    ) -> List[GeneratedTaskRecord]:
        """Release generation locks and any task waiting on a return pickup."""
        state = _clean_text(state).lower()
        direct = self.direct_volume_requests.get(task.id)
        if direct and direct['status'] == 'pending' and not getattr(task, 'is_return_task', False):
            if state == 'completed':
                direct['status'] = 'completed'
            elif state == 'failed':
                direct['status'] = ('unconfirmed' if getattr(task, 'payload_instance_picked_up', False)
                                    else 'failed_before_pickup')
        item_key = _clean_text(getattr(task, 'generator_item_key', ''))
        item_runtime = self.item_runtime.get(item_key)
        if item_runtime and not getattr(task, 'is_return_task', False):
            request = item_runtime['requests'].get(task.id)
            delivered = state == 'tracked_items_delivered' or (state == 'completed' and not getattr(task, 'dropoff_zone', ''))
            if request and request['status'] == 'pending' and (delivered or state == 'failed'):
                instance = next(instance for instance in self.instances if instance['key'] == item_key)
                items = _payload_tracked_items(self.payloads.get(_clean_text(instance['cfg'].get('payload'))))
                self._advance_tracked_stock(instance,
                    item_runtime['last_update_time'] if event_time is None else event_time,
                    list(item_runtime['resource_quantities']), items)
                location = request['resource']
                if delivered:
                    removed = {}
                    for name, supplied in request['quantities'].items():
                        balance = item_runtime['balances'][location][name]
                        quantities = item_runtime['resource_quantities'][location]
                        removed[name] = 0.0
                        if request['mode'] == 'full_exchange':
                            removed[name] = quantities[name]
                            balance['removed'] += quantities[name]
                            quantities[name] = 0.0
                        quantities[name] += supplied
                        balance['delivered'] += supplied
                    task.generator_item_delivery_receipt = {
                        'rule_id': item_key, 'resource': location, 'mode': request['mode'],
                        'quantities': dict(request['quantities']), 'removed': removed,
                        'confirmation': state, 'consumption_time': item_runtime['last_update_time'],
                    }
                request['status'] = 'delivered' if delivered else 'failed'
                pending = item_runtime['pending_resources'].get(location, set())
                pending.discard(task.id)
                if not pending:
                    item_runtime['pending_resources'].pop(location, None)
        spacing_key = _clean_text(
            getattr(task, "generator_release_spacing_key", "")
        )
        collection_id = _clean_text(
            getattr(task, "generator_collection_task_id", "")
        ) or _clean_text(getattr(task, "id", ""))
        released: List[GeneratedTaskRecord] = []

        if state == "failed" and spacing_key:
            # A timed-out queued task must never be released when a preceding
            # return eventually clears the zone. Keep the live blocker intact.
            queue = self.deferred_release_queues.get(spacing_key, [])
            kept = [record for record in queue if record.task.id != task.id]
            if kept:
                self.deferred_release_queues[spacing_key] = kept
            else:
                self.deferred_release_queues.pop(spacing_key, None)

        if (
            state == "return_payload_picked_up"
            and bool(getattr(task, "is_return_task", False))
            and spacing_key
            and self.release_spacing_active.get(spacing_key) == collection_id
        ):
            released.extend(
                self._release_next_deferred_record(spacing_key, task.id)
            )
        elif (
            state == "failed"
            and not bool(getattr(task, "is_return_task", False))
            and not bool(getattr(task, "payload_instance_picked_up", False))
            and spacing_key
            and self.release_spacing_active.get(spacing_key) == collection_id
        ):
            # A delivery that failed before pickup never occupied the shared
            # zone, so it must not hold the lower-priority release queue.
            released.extend(
                self._release_next_deferred_record(spacing_key, "")
            )

        # Collection allocations are separate from return cycles and attempts.
        # Never count a return as fresh volume, or restore uncertain in-transit
        # waste to a source where it is no longer known to exist.
        volume_key = _clean_text(getattr(task, "generator_volume_key", ""))
        if not volume_key or bool(getattr(task, 'is_return_task', False)):
            return released
        runtime = self.runtime.get(volume_key)
        if not runtime:
            return released

        allocation = runtime.get('volume_collections', {}).get(task.id)
        if not allocation or allocation['status'] != 'pending':
            return released
        if state == 'completed':
            allocation['status'] = 'completed'
        elif state == 'failed':
            if bool(getattr(task, 'payload_instance_picked_up', False)):
                allocation['status'] = 'unconfirmed'
            else:
                runtime['volume'] += allocation['volume_m3']
                allocation['status'] = 'restored'
        return released

    def update_until(self, now: float) -> List[GeneratedTaskRecord]:
        generated: List[GeneratedTaskRecord] = []
        if not self.instances:
            return generated

        for instance in self.instances:
            generated.extend(self._timeframe_records(instance, now))
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
    - departments[].operating_start_time / operating_end_time
    - departments[].hours_operated_per_day (derived compatibility field)
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
                    "volume_collections": {},
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
        return _department_is_open_at_datetime(
            dept, self.clock.sim_seconds_to_datetime(sim_time_sec)
        )

    def _department_active_elapsed_seconds(
        self, dept: dict, start_sec: float, end_sec: float
    ) -> float:
        return _department_active_seconds_between(
            dept,
            self.clock.sim_seconds_to_datetime(start_sec),
            self.clock.sim_seconds_to_datetime(end_sec),
        )

    def _department_hourly_waste_rate_m3(self, dept: dict) -> float:
        from amr_generation_inputs import department_waste_hourly_rate
        return department_waste_hourly_rate(dept)

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
            rule_id=f'legacy_waste:{dept_id}:{stream_name}',
        )

    def waste_volume_balance(self):
        return [_waste_balance_row(f'legacy_waste:{department}:{stream}', self.generator_type,
                    runtime['generated_m3_total'], runtime['fill_m3'],
                    list(runtime['volume_collections'].values()))
                for department, streams in sorted(self.runtime.items())
                for stream, runtime in sorted(streams.items())]

    def task_state_changed(self, task, state, event_time=None):
        if getattr(task, 'is_return_task', False):
            return []
        key = getattr(task, 'legacy_waste_allocation_key', None)
        if not key:
            return []
        runtime = self.runtime.get(key[0], {}).get(key[1])
        if runtime is None:
            return []
        allocation = runtime['volume_collections'].get(task.id)
        if not allocation or allocation['status'] != 'pending':
            return []
        if state == 'completed':
            allocation['status'] = 'completed'
        elif state == 'failed':
            if getattr(task, 'payload_instance_picked_up', False):
                allocation['status'] = 'unconfirmed'
            else:
                runtime['fill_m3'] += allocation['volume_m3']
                allocation['status'] = 'restored'
        return []

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

                elapsed_hours = (
                    self._department_active_elapsed_seconds(dept, last_time, now)
                    / 3600.0
                )
                generated_m3 = max(
                    0.0, elapsed_hours * self._department_hourly_waste_rate_m3(dept)
                )
                runtime["fill_m3"] += generated_m3
                runtime["generated_m3_total"] += generated_m3

                if self._department_is_active(dept, now):
                    trigger_volume_m3 = float(
                        runtime.get("container_capacity_m3", 0.0) or 0.0
                    ) * float(runtime.get("full_threshold_fraction", 0.8) or 0.8)

                    if trigger_volume_m3 > 0:
                        while (runtime["fill_m3"] >= trigger_volume_m3 or
                               math.isclose(runtime["fill_m3"], trigger_volume_m3, rel_tol=1e-12, abs_tol=0)):
                            record = self._create_task_record(
                                dept=dept,
                                stream_name=stream_name,
                                release_time=now,
                                waste_volume_m3=trigger_volume_m3,
                            )
                            if record is None:
                                break  # Retain fill when no collection can be represented.
                            record.task.legacy_waste_allocation_key = (dept_id, stream_name)
                            runtime['volume_collections'][record.task.id] = {
                                'task_id': record.task.id, 'rule_id': record.rule_id,
                                'volume_m3': trigger_volume_m3, 'status': 'pending',
                                'requested_pickup': record.task.pickup,
                                'requested_dropoff': record.task.dropoff,
                            }
                            generated.append(record)
                            runtime["fill_m3"] = max(0.0, runtime["fill_m3"] - trigger_volume_m3)
                            runtime["tasks_created"] += 1

                runtime["last_update_time"] = now

        return generated


class SharedContainerConflictError(ValueError):
    """Active contributors disagree on the definition of one shared container."""

    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__('; '.join(conflicts))


def shared_container_conflicts(instances):
    """Compare resolved rules, so checks and runtime use identical precedence."""
    groups = {}
    conflicts = []
    for instance in instances:
        cfg = instance.get('cfg', {})
        group = _clean_text(instance.get('container_group'))
        if (not cfg.get('enabled', False)
                or not instance.get('department', {}).get('enabled', True)
                or not group.startswith(('shared:', 'pickup:'))):
            continue
        definition = {
            'payload': _clean_text(cfg.get('payload')),
            'container_capacity_m3': _as_float(cfg.get('container_capacity_m3', 0)),
            'threshold_volume_m3': _as_float(cfg.get('threshold_volume_m3', 0)),
            'initial_container_present': bool(cfg.get('initial_container_present', True)),
        }
        if group not in groups:
            groups[group] = (instance['key'], definition)
            continue
        first_key, first_definition = groups[group]
        for field, value in definition.items():
            if first_definition[field] != value:
                conflicts.append(
                    f"Shared container {group!r} has conflicting {field}: "
                    f"{first_key} uses {first_definition[field]!r}; {instance['key']} uses {value!r}. "
                    'Use one container definition or separate group identifiers.'
                )
    return conflicts


class TaskGenerationManager:
    """Registry and coordinator for all runtime task generators."""

    def __init__(
        self,
        config: dict,
        clock: SimulationClock,
        locations: Dict[str, Location],
        payloads: Dict[str, PayloadType],
        *, prepare_runtime: bool = True,
    ):
        self.config = config or {}
        self.clock = clock
        self.locations = locations
        self.payloads = payloads
        self.generators: List[BaseTaskGenerator] = []
        from amr_generation_inputs import validate_generation_inputs
        validate_generation_inputs(config)
        self._build_generators(prepare_runtime=prepare_runtime)
        conflicts = shared_container_conflicts(
            instance for generator in self.generators
            if isinstance(generator, DynamicCategoryTaskGenerator)
            for instance in generator.instances
        )
        if conflicts:
            raise SharedContainerConflictError(conflicts)

    def _task_generation_cfg(self) -> dict:
        return self.config.get("task_generation", {}) or {}

    def waste_volume_balance(self):
        return [row for generator in self.generators
                if isinstance(generator, (DynamicCategoryTaskGenerator, DepartmentWasteTaskGenerator))
                for row in generator.waste_volume_balance()]

    def tracked_item_balance(self):
        return [row for generator in self.generators
                if isinstance(generator, DynamicCategoryTaskGenerator)
                for row in generator.tracked_item_balance()]

    def direct_volume_balance(self):
        return [row for generator in self.generators if isinstance(generator, DynamicCategoryTaskGenerator)
                for row in generator.direct_volume_balance()]

    def tracked_item_requests(self):
        return [{'rule_id': rule, 'task_id': task_id, **request, 'quantities': dict(request['quantities'])}
                for generator in self.generators if isinstance(generator, DynamicCategoryTaskGenerator)
                for rule, runtime in generator.item_runtime.items()
                for task_id, request in runtime.get('requests', {}).items()]

    def initial_waste_container_definitions(self):
        """Resolved modern Waste stock, or None for the legacy seed adapter.

        An enabled modern rule owns its initial bins, even when the global
        generation switch disables that rule. Do not revive raw department stock
        in that case. Legacy/custom waste services retain their existing adapter.
        """
        category = (self._task_generation_cfg().get('categories', {}) or {}).get('waste', {})
        if not self._category_has_enabled_rule(category):
            return None
        definitions = []
        for generator in self.generators:
            if not isinstance(generator, DynamicCategoryTaskGenerator):
                continue
            for instance in generator.instances:
                cfg = instance['cfg']
                if (instance.get('category_key') != 'waste' or not instance.get('waste_stream')
                        or not cfg.get('enabled', False)
                        or not instance.get('department', {}).get('enabled', True)
                        or not cfg.get('initial_container_present', True)):
                    continue
                definitions.append({
                    'department_id': instance['department_id'],
                    'waste_stream': instance['waste_stream'],
                    'payload': cfg['payload'],
                    'container_group': instance['container_group'],
                    'pickup_locations': list(instance['pickup_locations']),
                })
        return definitions

    def _generation_enabled(self, name: str, default: bool = True) -> bool:
        cfg = self._task_generation_cfg()
        if cfg and not bool(cfg.get("enabled", True)):
            return False
        specific = cfg.get(name, {}) or {}
        return bool(specific.get("enabled", default))

    def _has_dynamic_categories(self) -> bool:
        categories = self._task_generation_cfg().get("categories", {}) or {}
        return any(self._category_has_enabled_rule(category) for category in categories.values())

    @staticmethod
    def _category_has_enabled_rule(category: dict) -> bool:
        """Groups are independent services, just like department overrides."""
        if not isinstance(category, dict):
            return False
        if bool(category.get("enabled", False)):
            return True
        overrides = category.get("departments", {})
        if isinstance(overrides, dict) and any(
            isinstance(value, dict) and bool(value.get("enabled", False))
            for value in overrides.values()
        ):
            return True
        groups = category.get("department_groups", [])
        return isinstance(groups, list) and any(
            isinstance(group, dict) and bool(group.get("departments"))
            and isinstance(group.get("payload"), dict)
            and bool(group["payload"].get("enabled", False))
            for group in groups
        )

    def _build_generators(self, *, prepare_runtime=True) -> None:
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
                    prepare_runtime=prepare_runtime,
                    waste_streams=waste_streams,
                    waste_stream_paths={str(item.get('name', '')).strip(): f'/waste_streams/{i}'
                                        for i, item in enumerate(self.config.get('waste_streams', []))
                                        if str(item.get('name', '')).strip()},
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
        dynamic_waste_enabled = self._category_has_enabled_rule(waste_category)

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

    def scheduled_wake_times(self, horizon: float) -> List[float]:
        return sorted({time for generator in self.generators
                       for time in generator.scheduled_wake_times(horizon)})

    def update_schedules_until(self, now: float) -> List[GeneratedTaskRecord]:
        generated = []
        for generator in self.generators:
            generated.extend(generator.update_schedules_until(now))
        return generated

    def task_state_changed(
        self, task: Task, state: str, event_time: Optional[float] = None
    ) -> List[GeneratedTaskRecord]:
        """Forward task completion/failure state to every runtime generator."""
        released: List[GeneratedTaskRecord] = []
        for generator in self.generators:
            released.extend(generator.task_state_changed(task, state, event_time=event_time) or [])
        return released
