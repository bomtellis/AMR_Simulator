"""Recurring FM release settings shared by generation, preview and runtime."""
from bisect import bisect_left
from datetime import date, datetime, time, timedelta
from math import isfinite

STRATEGIES = {
    "current": "Current Task Generation timings",
    "manual": "Your sequence",
    "outbound": "Shortest outbound first",
    "round_trip": "Shortest round trip first",
    "slack": "Least deadline slack first",
    "coordinated": "Coordinated waves",
}


def clock_time(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("Enter a time as HH:MM.")
    return time(int(value[:2]), int(value[3:]))


def validate_fm_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("FM logistics settings must be an object.")
    if "enabled" in settings and not isinstance(settings["enabled"], bool):
        raise ValueError("Enable FM logistics must be true or false.")
    categories = settings.get("categories", {})
    if not isinstance(categories, dict):
        raise ValueError("FM logistics categories must be an object.")
    for key, category in categories.items():
        if not isinstance(category, dict):
            raise ValueError(f"{key}: expected category settings.")
        hold = category.get("hold_seconds", 0)
        if type(hold) not in (int, float) or not isfinite(hold) or not 0 <= hold <= 3600:
            raise ValueError(f"{key}: maximum hold must be between 0 and 60 minutes.")
        cohorts = category.get("cohorts", [])
        if not isinstance(cohorts, list):
            raise ValueError(f"{key}: expected a list of cohorts.")
        names, departments = set(), set()
        for cohort in cohorts:
            if not isinstance(cohort, dict):
                raise ValueError(f"{key}: expected a cohort object.")
            name = cohort.get("id")
            members = cohort.get("departments", [])
            if not isinstance(name, str) or not name.strip() or "|" in name or name in names:
                raise ValueError(f"{key}: cohort names must be unique and cannot contain |.")
            if not isinstance(members, list) or any(not isinstance(member, str) for member in members):
                raise ValueError(f"{key}: enter department IDs for each cohort.")
            for member in members:
                if member in departments:
                    raise ValueError(f"{key}: department {member} appears in more than one cohort.")
                departments.add(member)
            names.add(name)
        slots = category.get("slots", {})
        if not isinstance(slots, dict):
            raise ValueError(f"{key}: expected an object of recurring slots.")
        for slot, window in slots.items():
            if slot.startswith("timeframe/"):
                _, native_start, native_end = slot.split("/")
                clock_time(native_start)
                if native_end != "24:00":
                    clock_time(native_end)
            elif slot != "timeframe":
                clock_time(slot)
            if not isinstance(window, dict):
                raise ValueError(f"{key} {slot}: expected a dispatch window.")
            earliest = clock_time(window.get("earliest"))
            due = clock_time(window.get("deadline"))
            span = (_seconds(due) - _seconds(earliest)) % 86400
            if not span:
                raise ValueError(f"{key} {slot}: earliest dispatch and service deadline must differ.")
            offsets = window.get("offsets", {})
            if not isinstance(offsets, dict):
                raise ValueError(f"{key} {slot}: expected a set of wave offsets.")
            for cohort, offset in offsets.items():
                if cohort not in names or type(offset) not in (int, float) or not isfinite(offset) or not 0 <= offset < span:
                    raise ValueError(f"{key} {slot}: wave offsets must fit inside the dispatch window.")


def _seconds(value):
    return value.hour * 3600 + value.minute * 60


def windows_for_day(window, nominal_day, start, *, timeframe=False):
    day = date.fromisoformat(nominal_day)
    due = datetime.combine(day, clock_time(window["deadline"]), start.tzinfo)
    earliest = datetime.combine(day, clock_time(window["earliest"]), start.tzinfo)
    if earliest >= due:
        if timeframe:
            due += timedelta(days=1)
        else:
            earliest -= timedelta(days=1)
    return (earliest - start).total_seconds(), (due - start).total_seconds()


def category_policy(generation, category):
    if not generation.get("enabled", True):
        return {}
    plan = generation.get("fm_logistics", {})
    return plan.get("categories", {}).get(category, {}) if plan.get("enabled") else {}


def planned_release(policy, department, slot, nominal_day, start):
    slots = policy.get("slots", {})
    timeframe = slot.startswith("timeframe")
    window = slots.get(slot) or (slots.get("timeframe") if timeframe else None)
    if not window:
        return None
    for cohort in policy.get("cohorts", []):
        if department in cohort["departments"] and cohort["id"] in window.get("offsets", {}):
            earliest, deadline = windows_for_day(window, nominal_day, start, timeframe=timeframe)
            return earliest + window["offsets"][cohort["id"]], deadline, cohort["id"]
    return None


def mark_task(task, original, timing):
    release, deadline, cohort = timing
    task.fm_original_release = original
    task.fm_planned_release = release
    task.fm_deadline = deadline
    task.fm_cohort_id = cohort
    task.target_time = deadline - release


def task_tags(task):
    category = getattr(task, "staff_category_key", "")
    if not category and getattr(task, "task_source", "") == "department_waste":
        category = "waste"
    return {
        "category": category,
        "cohort": getattr(task, "fm_cohort_id", ""),
        "return": bool(getattr(task, "is_return_task", False)),
    }


def legacy_category(task_id, source=""):
    import re

    match = re.match(r"^(?:(?:RETURN[-_])+)?GEN_(CATERING|PHARMACY|LINEN|WASTE|STORES|SSD)_",
                     task_id, re.I)
    if match:
        return match[1].lower()
    return "waste" if source == "department_waste" else ""


def compatible_robots(sim, payload):
    """One representative of each configured robot type and allowed orientation."""
    seen = set()
    for robot in sim.amrs:
        for slot in sim._runtime_amr_payload_slots(robot):
            for orientation in sim._compatible_payload_orientations(payload, slot):
                key = (robot.id.rsplit("-", 1)[0], orientation)
                if key not in seen:
                    seen.add(key)
                    yield robot, orientation


def reactive_hold(sim, task, now, latest, instance, generator):
    """Return the next safer eligibility check and a reason."""
    flags = ("tracked_item_exchange", "requires_staff", "generator_waits_for_return",
             "release_next_after_return_pickup", "requires_existing_payload_instance",
             "shared_container", "requires_existing_waste_container")
    if (any(getattr(task, flag, False) for flag in flags) or getattr(task, "dropoff_zone", "")
            or task.waste_stream or getattr(task, "container_group", "")
            or any(sim._location_has_payload_inventory_spaces(name) for name in (task.pickup, task.dropoff))):
        return now, "Existing staff, stock, container or dependency constraints"
    pickup, dropoff = (sim.locations.get(name) for name in (task.pickup, task.dropoff))
    payload = sim._payload_for_task(task)
    if not pickup or not dropoff or not payload or pickup.floor == dropoff.floor:
        return now, "No eligible cross-floor route"
    rules = sim._resolve_task_route_rules(task)
    options = list(compatible_robots(sim, payload))
    if not options:
        return now, "No compatible robot"

    def quote(at):
        from amr_floor_routing import lift_plan_journeys

        alternatives = []
        for robot, orientation in options:
            plan = sim._nearest_compatible_lift_plan(
                at + sim.load_unload_time_sec, robot, pickup, dropoff, payload,
                rules, orientation, collect_segments=False)
            if plan:
                wait = sum(journey["wait_time"] for journey in lift_plan_journeys(plan))
                alternatives.append((plan["final_finish"] + sim.load_unload_time_sec, wait))
        return min(alternatives, default=(float("inf"), 0))

    def wave_count(at):
        # Future planned releases are recurring calendar entries, even before task creation.
        return sum(bisect_left(calendar["entries"], (at + 60,))
                   - bisect_left(calendar["entries"], (at,))
                   for calendar in generator._schedule_calendars.values())

    now_finish, now_wait = quote(now)
    if not isfinite(now_finish) or (task.fm_deadline is not None and now_finish >= task.fm_deadline):
        return now, "No proven time before deadline"
    candidate = min(now + 60, latest)
    if candidate <= now or not generator._instance_is_active(instance, candidate):
        return now, "Hold limit or operating window reached"
    later_finish, later_wait = quote(candidate)
    if (not isfinite(later_finish) or later_finish > sim.task_generation_horizon_sec
            or (task.fm_deadline is not None and later_finish > task.fm_deadline)):
        return now, "Deadline or run horizon would be at risk"
    if later_wait + 15 * wave_count(candidate) < now_wait + 15 * wave_count(now):
        return candidate, "Held for a less congested lift window"
    return now, "No lower-contention lift window"
