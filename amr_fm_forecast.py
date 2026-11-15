"""Compare recurring release policies on a shared, private lift booking model."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from heapq import heappop, heappush
from itertools import count
from math import inf, isfinite

from amr_demand_preview import build_demand_preview
from amr_floor_routing import lift_plan_journeys
from amr_fm_logistics import STRATEGIES, compatible_robots, planned_release, validate_fm_settings, windows_for_day
from amr_route_reservations import LiftReservations
from amr_sim_models import Task
from visualiser.project_checks import config_fingerprint


def native_demand(config):
    baseline = deepcopy(config)
    baseline.setdefault("task_generation", {}).pop("fm_logistics", None)
    # The separate human contingency study has its own carrying-profile validation.
    baseline.pop("human_contingency", None)
    return build_demand_preview(baseline)


def initial_policy(preview, category, workloads=None):
    rows = [row for row in preview["tasks"] if row["category"] == category
            and row["effective_task"].get("fm_slot")]
    members = defaultdict(float)
    for row in rows:
        key = row["department"]
        if key:
            members[key] += (workloads or {}).get((row["pickup"], row["dropoff"]), row["quantity"])
    groups = [{"id": f"{category}-{index + 1}", "departments": []} for index in range(3)]
    loads = [0.0] * len(groups)
    for department, weight in sorted(members.items(), key=lambda item: (-item[1], item[0])):
        index = min(range(len(groups)), key=lambda i: (loads[i], len(groups[i]["departments"]), i))
        groups[index]["departments"].append(department)
        loads[index] += weight
    slots = {}
    by_slot = defaultdict(list)
    start = datetime.fromisoformat(preview["start_datetime"])
    for row in rows:
        task = row["effective_task"]
        by_slot[task["fm_slot"]].append(task)
    for slot, tasks in by_slot.items():
        if slot.startswith("timeframe"):
            def relative(task, key):
                midnight = datetime.fromisoformat(task["fm_nominal_day"]).replace(tzinfo=start.tzinfo)
                return float(task[key]) - (midnight - start).total_seconds()

            first = max(relative(task, "staff_work_window_start") for task in tasks)
            last = min(relative(task, "timeframe_deadline_time") for task in tasks)
            if last - first < 60:
                continue
            midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
            earliest = (midnight + timedelta(minutes=-(-first // 60))).strftime("%H:%M")
            deadline = (midnight + timedelta(minutes=last // 60)).strftime("%H:%M")
        else:
            deadline = slot
            earliest = (datetime.strptime(slot, "%H:%M") - timedelta(minutes=30)).strftime("%H:%M")
        span = (datetime.strptime(deadline, "%H:%M") - datetime.strptime(earliest, "%H:%M")).total_seconds() % 86400
        spacing = min(300, span / 4)
        slots[slot] = {"earliest": earliest, "deadline": deadline,
                       "offsets": {group["id"]: index * spacing for index, group in enumerate(groups)}}
    return {"cohorts": groups, "slots": slots, "hold_seconds": 0}


def suggest_policy(config, preview, category):
    engine = LiftForecast(config)
    work = {}
    for row in preview["tasks"]:
        if row["category"] != category or not row["effective_task"].get("fm_slot"):
            continue
        key = row["pickup"], row["dropoff"]
        if key not in work:
            service = engine.service(row)
            work[key] = service["outbound_cost"] if isfinite(service["outbound_cost"]) else 1.0
    return initial_policy(preview, category, work)


class LiftForecast:
    def __init__(self, config):
        from simulator import Simulation

        model = deepcopy(config)
        model.setdefault("task_generation", {}).pop("fm_logistics", None)
        model["simulation"]["precompute_static_routes"] = False
        self.sim = Simulation(model, verbose=False)
        self.start = self.sim.clock.start_datetime
        self.original_lifts = deepcopy(self.sim.lifts)
        self.routes = {}
        self.robots = {}
        self.serial = count()

    def route(self, task, reverse=False):
        sim = self.sim
        source, target = (task.dropoff, task.pickup) if reverse else (task.pickup, task.dropoff)
        payload_name = (task.return_payload or task.payload) if reverse else task.payload
        if reverse:
            route_task = Task(id=task.id, pickup=source, dropoff=target, payload=payload_name,
                              route_profile=task.return_route_profile or task.route_profile, labels=task.labels)
        else:
            route_task = task
        rules = sim._resolve_task_route_rules(route_task)
        key = (source, target, payload_name, sim._rules_cache_key(rules))
        if key in self.routes:
            return self.routes[key]
        pickup, dropoff = sim.locations.get(source), sim.locations.get(target)
        payload = sim._payload_for_task(route_task)
        options = []
        if pickup and dropoff and payload:
            if payload_name not in self.robots:
                self.robots[payload_name] = list(compatible_robots(sim, payload))
            for robot, orientation in self.robots[payload_name]:
                if pickup.floor == dropoff.floor:
                    route = sim._same_floor_segments(robot, pickup, dropoff, rules=rules,
                                                    payload=payload, orientation=orientation,
                                                    collect_segments=False)
                    if route is not None:
                        options.append((float(route[1]), []))
                    continue
                from amr_floor_routing import required_waypoint

                if required_waypoint(sim.config, pickup.floor, dropoff.floor) in (None, dropoff.floor):
                    for lift in sim.lifts:
                        plan = sim._direct_lift_plan(0, robot, pickup, dropoff, payload, rules,
                                                     orientation, False, only_lift=lift.id)
                        if plan:
                            options.append(self._legs(plan))
                if not options:
                    plan = sim._nearest_compatible_lift_plan(0, robot, pickup, dropoff, payload,
                                                             rules, orientation, False)
                    if plan:
                        options.append(self._legs(plan))
        # Identical robot capacities and speeds can yield identical choices.
        unique = {tuple(legs): (duration, legs) for duration, legs in
                  sorted(options, key=lambda option: -option[0])}
        self.routes[key] = list(unique.values())
        return self.routes[key]

    @staticmethod
    def _legs(plan):
        return plan["final_finish"], [
            (row["lift"].id, row["origin_lift"].floor, row["destination_lift"].floor,
             row["to_lift_sec"], row["from_lift_sec"]) for row in lift_plan_journeys(plan)
        ]

    def service(self, row):
        fields = Task.__dataclass_fields__
        data = {key: value for key, value in row["effective_task"].items() if key in fields}
        data.setdefault("id", row["preview_id"])
        task = Task(**data)
        outbound = self.route(task)
        returns = self.route(task, True) if task.return_enabled and outbound else []
        final = task.final_destination or task.dropoff
        handling = 0.0
        if final != task.dropoff:
            walk, _, _ = self.sim._staff_travel_between_locations(task.dropoff, final)
            handling = walk + task.staff_collection_delay_minutes * 60
        load = 2 * self.sim.load_unload_time_sec
        outbound_cost = min((option[0] for option in outbound), default=inf) + load + handling
        return_cost = min((option[0] for option in returns), default=0) + (load + handling if returns else 0)
        return dict(row, outbound=outbound, returns=returns, outbound_cost=outbound_cost,
                    round_trip=outbound_cost + return_cost, handoff=handling, final=final)

    def evaluate(self, services, plan, *, current=False):
        sim = self.sim
        sim.lifts = deepcopy(self.original_lifts)
        lifts = {lift.id: lift for lift in sim.lifts}
        sim.lift_reservations = {lift_id: LiftReservations() for lift_id in lifts}
        load = sim.load_unload_time_sec
        queue, rows = [], []
        totals = defaultdict(Counter)
        buckets = Counter()

        def add(lift_id, kind, start, finish, origin, destination, summary):
            direction = "up" if destination > origin else "down" if destination < origin else "same_floor"
            summary[f"{kind}_{direction}"] += 1
            for minute in range(int(start // 300), int(finish // 300) + 1):
                buckets[lift_id, minute] += max(0.0, min(finish, (minute + 1) * 300) - max(start, minute * 300))

        for service in services:
            task = service["effective_task"]
            category = service["category"]
            rule = plan["categories"].get(category, {})
            slot, day = task.get("fm_slot"), task.get("fm_nominal_day")
            release = service["release_seconds"]
            target = float(task.get("target_time", 0) or 0)
            deadline = task.get("timeframe_deadline_time", release + target if target > 0 else None)
            cohort = ""
            if slot and day:
                timing = planned_release(rule, service["department"], slot, day, self.start)
                if timing:
                    new_release, deadline, cohort = timing
                    if not current:
                        release = new_release
            heappush(queue, (release, next(self.serial), False, service, deadline, cohort))

        while queue:
            release, _, returning, service, deadline, cohort = heappop(queue)
            category = service["category"]
            task = service["effective_task"]
            summary = totals[category]
            kind = "return" if returning else "outbound"
            summary["projected_returns" if returning else "tasks"] += 1
            if not returning:
                summary["payloads"] += service["quantity"]
            options = service["returns"] if returning else service["outbound"]
            winner = (inf, [])
            for duration, legs in options:
                time = release + load
                bookings = []
                for lift_id, origin, destination, approach, exit_time in legs:
                    lift = lifts[lift_id]
                    time += approach
                    slot = sim._find_lift_journey_slot(lift, time, origin, destination,
                                                      prior_journeys=bookings)
                    if not isfinite(slot["lift_finish"]):
                        time = inf
                        break
                    slot.update(lift=lift, origin_lift=sim._lift_location_on_floor(lift, origin),
                                destination_lift=sim._lift_location_on_floor(lift, destination),
                                arrival=time)
                    bookings.append(slot)
                    time = slot["lift_finish"] + exit_time
                finish = time + load if legs else time + duration + load
                if finish < winner[0]:
                    winner = finish, bookings
            finish, bookings = winner
            if not isfinite(finish):
                summary["unresolved"] += 1
            elif not bookings:
                summary[f"{kind}_same_floor"] += 1
            for slot in bookings:
                lift_id = slot["lift"].id
                origin, destination = slot["origin_lift"].floor, slot["destination_lift"].floor
                if slot["reposition_sec"]:
                    add(lift_id, "reposition", slot["lift_start"], slot["reposition_finish"],
                        slot["reposition_from_floor"], origin, summary)
                add(lift_id, kind, slot["reposition_finish"], slot["lift_finish"], origin, destination, summary)
                summary["lift_wait_seconds"] += slot["lift_start"] - slot["arrival"]
                sim._reserve_lift_journey(slot)
            if returning:
                continue
            arrival = finish + service["handoff"]
            late = isfinite(arrival) and deadline is not None and arrival > deadline
            summary["late"] += int(late)
            rows.append(dict(service, planned=release, deadline=deadline, cohort=cohort,
                             estimated_arrival=arrival if isfinite(arrival) else None))
            if isfinite(arrival) and task.get("return_enabled"):
                ready = arrival
                if category == "catering" and cohort and deadline is not None:
                    ready = max(ready, deadline)
                ready += 60 * (task.get("return_delay_minutes") or 0) + service["handoff"]
                heappush(queue, (ready, next(self.serial), True, service, None, cohort))
        total = sum(totals.values(), Counter())
        total["peak_lift_seconds"] = max(buckets.values(), default=0)
        return {"rows": rows, "totals": dict(total), "categories": dict(totals)}


def candidate_settings(plan, services, start, strategy):
    candidate = deepcopy(plan)
    wave_load = Counter()
    if strategy == "coordinated":
        for row in services:
            task = row["effective_task"]
            policy = plan["categories"].get(row["category"], {})
            slot = task.get("fm_slot")
            if not slot or not planned_release(policy, row["department"], slot, task["fm_nominal_day"], start):
                if row["outbound"] and any(legs for _, legs in row["outbound"]):
                    wave_load[int(row["release_seconds"] // 300) % 288] += row["outbound_cost"]
    for category, policy in sorted(candidate["categories"].items()):
        for slot, window in sorted(policy.get("slots", {}).items()):
            rows = [row for row in services if row["category"] == category
                    and row["effective_task"].get("fm_slot") == slot]
            if not rows:
                continue
            day = rows[0]["effective_task"]["fm_nominal_day"]
            earliest, deadline = windows_for_day(window, day, start, timeframe=slot.startswith("timeframe"))
            span = deadline - earliest
            offsets = window.get("offsets", {})
            spacing = min((b - a for a, b in zip(sorted(offsets.values()), sorted(offsets.values())[1:]) if b > a),
                          default=min(300.0, span / 4))
            groups = []
            for cohort in policy.get("cohorts", []):
                group = [row for row in rows if row["department"] in cohort["departments"]]
                if group:
                    longest = max(row["outbound_cost"] for row in group)
                    round_trip = max(row["round_trip"] for row in group)
                    groups.append((cohort["id"], longest, round_trip))
            if strategy == "slack":
                groups.sort(key=lambda group: (-group[1], group[0]))
            elif strategy in ("outbound", "round_trip"):
                groups.sort(key=lambda group: (group[1 if strategy == "outbound" else 2], group[0]))
            if strategy == "coordinated":
                groups.sort(key=lambda group: (-group[1], group[0]))
            last_offset = -spacing
            for cohort_id, longest, _ in groups:
                last = min(span - 1, span - longest) if isfinite(longest) else span - 1
                first = min(span - 1, max(0.0, last_offset + spacing))
                if strategy == "coordinated":
                    choices = [first + step * 60 for step in range(max(0, int((last - first) // 60)) + 1)]
                    offset = min(choices, key=lambda value: (wave_load[int((earliest + value) // 300) % 288], value))
                    wave_load[int((earliest + offset) // 300) % 288] += longest
                else:
                    offset = first
                offsets[cohort_id] = offset
                last_offset = offset
    return candidate


def compare(config, plan, preview=None):
    validate_fm_settings(plan)
    preview = preview or native_demand(config)
    engine = LiftForecast(config)
    services = [engine.service(row) for row in preview["tasks"]]
    results = []
    for strategy, label in STRATEGIES.items():
        settings = plan if strategy in ("current", "manual") else candidate_settings(plan, services, engine.start, strategy)
        results.append(dict(engine.evaluate(services, settings, current=strategy == "current"),
                            strategy=strategy, label=label, settings=settings))
    results.sort(key=lambda result: tuple(result["totals"].get(key, 0) for key in
                 ("unresolved", "late", "peak_lift_seconds", "lift_wait_seconds")))
    return {"results": results, "config_hash": config_fingerprint(config),
            "runtime": [rule for rule in preview["rules"] if rule.get("unknown_additional_demand")
                        or rule.get("status") == "runtime-dependent"]}


def validate_application(config, plan, baseline):
    """Validate dispatch against the generator's actual calendars and demand."""
    validate_fm_settings(plan)
    selected = deepcopy(config)
    selected.pop("human_contingency", None)
    selected.setdefault("task_generation", {})["fm_logistics"] = plan
    actual = build_demand_preview(selected)

    def identity(row):
        task = row["effective_task"]
        return (row["rule_id"], task.get("fm_slot"), task.get("fm_nominal_day"),
                row["pickup"], row["dropoff"], row["payload"], row["quantity"])

    departments = {row.get("id") or row.get("name") for row in config.get("departments", [])}
    for category, policy in plan["categories"].items():
        for cohort in policy.get("cohorts", []):
            unknown = set(cohort["departments"]) - departments
            if unknown:
                raise ValueError(f"{category} {cohort['id']}: unknown departments {', '.join(sorted(unknown))}.")
    expected = Counter(identity(row) for row in baseline["tasks"])
    found = Counter(identity(row) for row in actual["tasks"])
    if expected != found:
        raise ValueError("The release plan moves tasks outside the forecast period or operating calendar. "
                         "Adjust the windows or run dates.")
    for row in actual["tasks"]:
        task = row["effective_task"]
        deadline = task.get("fm_deadline")
        if deadline is not None and not row["release_seconds"] < deadline <= (
                datetime.fromisoformat(actual["end_datetime"]) -
                datetime.fromisoformat(actual["start_datetime"])).total_seconds():
            raise ValueError(f"{row['category']} {row['department']}: service deadline is outside the run.")


def actual_activity(path):
    """Read normal run evidence in chunks and keep movement counts at trip grain."""
    import json
    from pathlib import Path
    from amr_event_csv import read_event_csv
    from amr_fm_logistics import legacy_category
    from report.amr_report_analysis import extract_lift_movements

    path = Path(path)
    manifest = path.parent / "run_manifest.json"
    if manifest.is_file():
        saved = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if saved.get("status") == "partial":
            raise ValueError("Open a completed normal run to review whole-run activity.")
    tasks = {}
    arrivals = {}
    failed = set()
    blocked_handoffs = set()
    waits = Counter()
    source_columns = {"event_type", "task_id", "sim_time_sec", "details", "task_source",
                      "department_id", "payload", "to_location", "wait_time_sec",
                      "segment_type", "task_target_time_sec", "status"}

    kinds = {"task_released", "task_generated", "return_task_generated", "task_complete",
             "multi_stop_task_complete", "fm_department_arrival", "fm_handoff_blocked",
             "location_payload_enter", "task_failed"}
    for chunk in read_event_csv(path, chunksize=50000, usecols=lambda field: field in source_columns,
                                keep_default_na=False, dtype=str):
        event_rows = chunk["event_type"].isin(kinds)
        if "segment_type" in chunk:
            event_rows |= chunk["segment_type"].astype(str).str.contains("lift", regex=False)
        for event in chunk[event_rows].to_dict("records"):
            task_id, kind = event.get("task_id", ""), event.get("event_type", "")
            if not task_id:
                continue
            task_id = str(task_id)
            if kind == "task_released":
                time = float(event.get("sim_time_sec") or 0)
                try:
                    details = json.loads(event.get("details", ""))
                except (ValueError, TypeError):
                    details = {}
                if not isinstance(details, dict):
                    details = {}
                target = float(event.get("task_target_time_sec") or 0)
                category = details.get("category") or legacy_category(task_id, event.get("task_source")) or "unknown"
                tasks[task_id] = dict(id=task_id, category=category, actual_release=time,
                                      quantity=details.get("quantity", 1), original=details.get("original", time),
                                      planned=details.get("planned", time),
                                      deadline=details.get("deadline", time + target if target > 0 else None),
                                      hold_reason=details.get("hold_reason", ""),
                                      cohort=details.get("cohort", ""),
                                      final=details.get("final_destination", event.get("to_location")),
                                      handoff=details.get("handoff", False),
                                      department=event.get("department_id"), payload=event.get("payload"))
            elif kind in {"task_generated", "return_task_generated", "task_failed"} and task_id not in tasks:
                time = float(event.get("sim_time_sec") or 0)
                category = legacy_category(task_id, event.get("task_source")) or "unknown"
                tasks[task_id] = dict(id=task_id, category=category, actual_release=None, quantity=1,
                                      original=time, planned=time, deadline=None, hold_reason="", cohort="",
                                      final=event.get("to_location"), handoff=False,
                                      department=event.get("department_id"), payload=event.get("payload"))
            if kind in {"task_complete", "multi_stop_task_complete", "fm_department_arrival", "location_payload_enter"}:
                key = task_id, kind, str(event.get("to_location", ""))
                at = float(event.get("sim_time_sec") or 0)
                arrivals[key] = min(at, arrivals.get(key, inf))
            elif kind == "task_failed":
                failed.add(task_id)
            elif kind == "fm_handoff_blocked":
                blocked_handoffs.add(task_id)
            if "lift" in str(event.get("segment_type", "")):
                waits[task_id] += float(event.get("wait_time_sec") or 0)

    by_task = defaultdict(list)
    for (task_id, kind, location), at in arrivals.items():
        by_task[task_id].append((kind, location, at))
    totals = defaultdict(Counter)
    for task_id, row in tasks.items():
        if row["handoff"]:
            candidates = [at for kind, location, at in by_task[task_id]
                          if kind == "fm_department_arrival" or
                          (kind == "location_payload_enter" and location == row["final"])]
        else:
            candidates = [at for kind, location, at in by_task[task_id]
                          if kind in {"task_complete", "multi_stop_task_complete"}]
        arrival = min(candidates, default=None)
        row["arrival"] = arrival
        if task_id in blocked_handoffs:
            row["hold_reason"] = "No staffed window for the department handoff"
        row["status"] = ("failed" if task_id in failed else "uncompleted") if arrival is None else (
            "arrived" if row["deadline"] is None else "late" if arrival > row["deadline"] else "on time")
        totals[row["category"]].update({"tasks": 1, "payloads": row["quantity"], row["status"]: 1,
                                        "lift_wait_seconds": waits[task_id]})
    movements = extract_lift_movements(path)
    for row in movements.to_dict("records"):
        totals[row["service_category"]][f'{row["activity_type"]}_{row["direction"].lower()}'] += 1
    return {"tasks": list(tasks.values()), "categories": dict(totals), "totals": dict(sum(totals.values(), Counter()))}
