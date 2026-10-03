"""Non-mutating, structured project preflight shared by editor and launcher.

This is an incremental checker, not a complete schema or physical verification.
Operational constraints are warnings; malformed inputs and references are errors.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from amr_sim_payload_instances import normalise_payload_name
try:
    from . import check_dependencies as dependency_checks
except ImportError:
    import check_dependencies as dependency_checks


def config_fingerprint(config) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    kind: str
    path: str
    object_name: str
    message: str
    consequence: str
    action: str
    section: str
    target: str = ""

    @property
    def id(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:20]

    def to_dict(self):
        return {"id": self.id, **asdict(self)}


@dataclass
class CheckReport:
    config_hash: str
    findings: list[Finding]
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: set[str] = field(default_factory=set)
    finding_inputs: dict = field(default_factory=dict)
    check_groups: dict = field(default_factory=dict)
    external_files: dict = field(default_factory=dict)

    def is_stale(self, config):
        return (self.config_hash != config_fingerprint(config) or
                dependency_checks.current_drawings(self.external_files) != self.external_files)

    def changed_inputs(self, finding, config):
        recorded = self.finding_inputs.get(finding.id)
        if not recorded:
            return ['*'] if self.is_stale(config) else []
        return dependency_checks.changed_inputs(recorded, config, dependency_checks.current_drawings(self.external_files))

    def group_states(self, config):
        external = dependency_checks.current_drawings(self.external_files)
        keys = {key for value in self.check_groups.values() for key in value['inputs']}
        hashes = {key: dependency_checks.input_hash(config, key, external) for key in keys}
        return {key: {'label': value['label'], 'execution': value['execution'],
                      'changed_inputs': [name for name, checksum in value['inputs'].items() if hashes[name] != checksum]}
                for key, value in self.check_groups.items()}

    def finding_states(self, config):
        external = dependency_checks.current_drawings(self.external_files)
        keys = {key for inputs in self.finding_inputs.values() for key in inputs}
        hashes = {key: dependency_checks.input_hash(config, key, external) for key in keys}
        stale = self.is_stale(config)
        return {f.id: ([key for key, checksum in self.finding_inputs[f.id].items() if hashes[key] != checksum]
                       if f.id in self.finding_inputs else ['*'] if stale else []) for f in self.findings}

    def acknowledge_warnings(self):
        self.acknowledged = {f.id for f in self.findings if f.severity == "warning"}

    def can_run(self, config):
        return (not self.is_stale(config)
                and not any(f.severity == "error" for f in self.findings)
                and all(f.id in self.acknowledged for f in self.findings if f.severity == "warning"))

    def to_dict(self):
        return {"schema_version": 1, "config_sha256": self.config_hash,
                "checked_at_utc": self.checked_at,
                "findings": [f.to_dict() for f in self.findings],
                "acknowledged_warning_ids": sorted(self.acknowledged),
                "dependency_schema_version": 1,
                "finding_inputs": self.finding_inputs, "check_groups": self.check_groups,
                "external_drawing_availability": self.external_files,
                "scope": "Structural, reference, schedule, graph and payload-capacity preflight; not full simulator validation."}


def check_project(config, *, base_path=None, include_legacy=True) -> CheckReport:
    """Read raw input before normalisation; never repair or save it implicitly."""
    findings = []
    completed_groups = set()

    def add(code, severity, path, name, message, consequence, action,
            section="project", target="", kind=None):
        findings.append(Finding(code, severity, kind or ("invalid_input" if severity == "error" else "constraint"),
                                path, str(name), message, consequence, action, section, str(target)))

    def error(path, message, section="project", target="", code="INPUT"):
        add(code, "error", path, target or path or "Project", message,
            "The simulator may reject or misinterpret this input.", "Correct the highlighted setting.", section, target)

    def finish():
        rank = {"error": 0, "warning": 1, "info": 2}
        unique = {f.id: f for f in findings}
        ordered = sorted(unique.values(), key=lambda f: (rank[f.severity], f.path, f.code))
        external = dependency_checks.drawing_state(config, base_path)
        hashes = {}
        def capture(deps):
            for key in deps:
                if key not in hashes:
                    hashes[key] = dependency_checks.input_hash(config, key, external)
            return {key: hashes[key] for key in deps}
        return CheckReport(config_fingerprint(config), ordered,
            finding_inputs={f.id: capture(dependency_checks.dependencies(f)) for f in ordered},
            check_groups={key: {'label': label, 'execution': 'completed' if key in completed_groups else 'not_run',
                                'inputs': capture(deps)}
                          for key, (label, deps) in dependency_checks.GROUPS.items()}, external_files=external)

    completed_groups.add('structure')
    if not isinstance(config, dict):
        error("/", "The project must be a JSON object.")
        return finish()

    lists = {"locations", "payloads", "amrs", "lifts", "tasks", "departments", "waste_streams",
             "mass_collections", "people_movements", "floor_dxf_files", "floor_pdf_underlays"}
    maps = {"simulation", "building", "corridors", "route_profiles", "task_generation", "scenario_testing"}
    for key in sorted(lists | maps):
        if key not in config:
            if key in {"simulation", "building", "locations", "payloads", "amrs"}:
                error("/" + key, f"Required section '{key}' is missing.", key)
            continue
        expected = list if key in lists else dict
        if not isinstance(config[key], expected):
            error("/" + key, f"'{key}' must be a {'list' if expected is list else 'JSON object'}.", key)
        elif expected is list:
            for i, item in enumerate(config[key]):
                if not isinstance(item, dict):
                    error(f"/{key}/{i}", "Each entry must be a JSON object.", key)
    if findings:
        return finish()
    corridors = config.get("corridors", {})
    for key in ("nodes", "edges"):
        value = corridors.get(key, [])
        if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
            error(f"/corridors/{key}", "Expected a list of JSON objects.", "corridors")
    for name, profile in config.get("route_profiles", {}).items():
        if not isinstance(profile, dict):
            error(f"/route_profiles/{name}", "A route profile must be a JSON object.", "route_profiles", name)
    if findings:
        return finish()

    from amr_routing_inputs import routing_input_findings
    for path, message in routing_input_findings(config):
        error(path, message, path.split('/')[1], code="ROUTING_INPUT")
    if findings:
        return finish()

    from amr_generation_inputs import generation_input_findings
    from amr_lift_inputs import lift_input_findings
    completed_groups.add('lifts')
    for path, message in lift_input_findings(config, require_speed=True, require_complete=True):
        error(path, message, 'lifts', code='LIFT_INPUT')
    if any(f.severity == 'error' for f in findings):
        return finish()

    completed_groups.add('generation')
    for severity, path, message in generation_input_findings(config):
        section = path.split('/')[1]
        if severity == 'error':
            error(path, message, section, code='GENERATION_INPUT')
        else:
            add('GENERATION_UNSUPPORTED', 'warning', path, path, message,
                'The run uses the supported staff calendar behavior described in this finding.',
                'Use supported calendar settings or acknowledge this limitation.',
                section=section, kind='unsupported')
    if any(f.severity == 'error' for f in findings):
        return finish()

    # Detect invalid numeric values before JsonStore normalisation can clamp them.
    positive = {"length_m", "width_m", "height_m", "door_clear_width_m", "default_corridor_width_m",
                "default_door_clear_width_m", "speed_m_per_sec", "walking_speed_m_per_sec", "battery_capacity_kwh",
                "battery_charge_rate_kw", "payload_capacity_kg", "payload_length_capacity_m",
                "payload_width_capacity_m", "payload_height_capacity_m", "max_concurrency", "floor_height_m"}
    nonnegative = {"distance_m", "weight_kg", "load_unload_time_sec", "max_task_deferral_minutes",
                   "return_delay_minutes", "staff_handling_minutes", "staff_collection_delay_minutes", "quantity"}

    def walk(value, path="", section="project", target=""):
        if isinstance(value, dict):
            target = str(value.get("name", value.get("id", target)))
            for key, child in value.items():
                p = path + "/" + str(key).replace("~", "~0").replace("/", "~1")
                sec = section if path else str(key)
                if key in positive | nonnegative:
                    inferred_bay_dimension = (key in {'length_m', 'width_m', 'height_m'}
                                              and re.fullmatch(r'/locations/\d+/inventory_spaces/\d+', path))
                    must_be_positive = key in positive and not inferred_bay_dimension
                    try:
                        number = float(child)
                        if isinstance(child, bool) or not math.isfinite(number) or number < 0 or (must_be_positive and number == 0):
                            raise ValueError
                    except (TypeError, ValueError):
                        error(p, f"{key} must be a finite {'positive' if must_be_positive else 'non-negative'} number.", sec, target, "NUMBER")
                elif isinstance(child, float) and not math.isfinite(child):
                    error(p, "Non-finite numbers are not valid project input.", sec, target, "NUMBER")
                if key in {"quantity", "max_concurrency", "floor"}:
                    try:
                        if isinstance(child, bool) or not math.isfinite(float(child)) or float(child) != int(float(child)):
                            raise ValueError
                    except (TypeError, ValueError, OverflowError):
                        error(p, f"{key} must be a whole number.", sec, target, "INTEGER")
                if key in {"scheduled_times", "schedule_times", "start_time", "end_time", "operating_start_time", "operating_end_time", "timeframe_start", "timeframe_end"}:
                    times = child if isinstance(child, list) else (str(child).split(",") if key in {"scheduled_times", "schedule_times"} else [child])
                    for item in times:
                        if item in (None, ""):
                            continue
                        text = str(item).strip()
                        is_end = key in {"end_time", "operating_end_time", "timeframe_end"}
                        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text) and not (is_end and text == "24:00"):
                            error(p, f"Invalid clock time '{text}'; use HH:MM{' (24:00 is allowed here)' if is_end else ''}.", sec, target, "SCHEDULE")
                walk(child, p, sec, target)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + f"/{index}", section, target)

    walk(config)
    if not config['locations']:
        error('/locations', 'At least one location is required.', 'locations')
    for section, required in (("amrs", "speed_m_per_sec"), ("payloads", "weight_kg")):
        for i, row in enumerate(config[section]):
            if required not in row:
                error(f'/{section}/{i}/{required}', f'{required} is required.', section, row.get('id', row.get('name', '')))
    sim = config.get("simulation", {})
    dates = {}
    for key in ("start_datetime", "end_datetime"):
        if key == "start_datetime" or sim.get(key):
            try:
                dates[key] = datetime.fromisoformat(sim[key])
            except (KeyError, TypeError, ValueError):
                error(f"/simulation/{key}", f"{key} must be an ISO date and time.", "simulation", code="RUN_PERIOD")
    if len(dates) == 2:
        try:
            if dates["end_datetime"] <= dates["start_datetime"]:
                raise ValueError
        except (TypeError, ValueError):
            error("/simulation/end_datetime", "End must follow start and both dates must use compatible timezone offsets.", "simulation", code="RUN_PERIOD")

    completed_groups.add('values')
    from amr_robot_inputs import robot_input_findings
    completed_groups.add('robots')
    invalid_paths = {f.path for f in findings if f.severity == 'error'}
    for path, message in robot_input_findings(config, require_complete=True):
        if path not in invalid_paths:
            error(path, message, path.split('/')[1], code='ROBOT_INPUT')
    from amr_payload_inputs import payload_input_findings
    completed_groups.add('payloads')
    invalid_paths = {f.path for f in findings if f.severity == 'error'}
    for path, message in payload_input_findings(config, require_complete=True):
        if path not in invalid_paths:
            error(path, message, 'payloads', code='PAYLOAD_INPUT')
    from amr_location_inputs import location_input_findings
    completed_groups.add('locations')
    invalid_paths = {f.path for f in findings if f.severity == 'error'}
    for path, message in location_input_findings(config, require_complete=True):
        if path not in invalid_paths:
            error(path, message, 'locations', code='LOCATION_INPUT')
    from amr_fleet_allocation import charge_input_findings, configured_fleet_bay_plan
    completed_groups.add('charge_inputs')
    for path, message in charge_input_findings(config, check_references=True):
        error(path, message, 'building', code='CHARGE_INPUT')
    from amr_inventory_inputs import inventory_input_findings
    completed_groups.add('inventory')
    invalid_paths = {f.path for f in findings if f.severity == 'error'}
    for path, message in inventory_input_findings(config, check_references=True):
        if path not in invalid_paths:
            error(path, message, 'locations', code='INVENTORY_INPUT')
    if any(f.severity == 'error' for f in findings):
        return finish()
    names = {}
    by_collection = {}
    for section, rows, field_name in [(key, config.get(key, []), "id" if key in {"amrs", "lifts", "tasks", "departments"} else "name")
                                      for key in ("locations", "payloads", "amrs", "lifts", "tasks", "departments", "waste_streams")]:
        seen = set()
        by_collection[section] = seen
        for i, row in enumerate(rows):
            name = row.get(field_name, row.get('name') if section == 'departments' else None)
            if section == 'departments':
                from amr_department_inputs import department_identity
                name = department_identity(row)
            path = f"/{section}/{i}/{field_name}"
            if not isinstance(name, str) or not name.strip():
                error(path, f"A non-empty {field_name} is required.", section, code="IDENTIFIER")
                continue
            if name in seen:
                error(path, f"Duplicate {field_name}: {name}.", section, name, "DUPLICATE")
            seen.add(name)
            if section == "locations":
                names[name] = row
    for i, node in enumerate(corridors.get("nodes", [])):
        name = node.get("name")
        if not isinstance(name, str) or not name.strip():
            error(f"/corridors/nodes/{i}/name", "A node name is required.", "corridors", code="IDENTIFIER")
        elif name in names:
            error(f"/corridors/nodes/{i}/name", f"Duplicate graph point: {name}.", "corridors", name, "DUPLICATE")
        else:
            names[name] = node
    lift_pairs = []
    for i, lift in enumerate(config.get("lifts", [])):
        floors = lift.get("floor_locations", {})
        if not isinstance(floors, dict):
            error(f"/lifts/{i}/floor_locations", "Lift floor locations must be a JSON object.", "lifts", lift.get("id", ""))
            continue
        points = []
        for floor, position in floors.items():
            try:
                floor_number = int(floor)
                if str(floor_number) != str(floor) or not isinstance(position, dict):
                    raise ValueError
            except (TypeError, ValueError):
                error(f"/lifts/{i}/floor_locations/{floor}", "Lift floor must be an integer with an x/y position.", "lifts", lift.get("id", ""))
                continue
            name = f"{lift.get('id', '')}-F{floor}"
            if name in names:
                error(f"/lifts/{i}/floor_locations/{floor}", f"Duplicate graph point: {name}.", "lifts", name, "DUPLICATE")
            names[name] = {**position, "floor": floor_number}
            points.append(name)
        lift_pairs.extend((a, b, lift.get("id", "")) for a in points for b in points if a != b)
    for name, point in names.items():
        for key in ("floor", "x", "y"):
            try:
                number = float(point[key])
                if not math.isfinite(number) or (key == "floor" and number != int(number)):
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                error(f"/points/{name}/{key}", f"Graph point {name} needs a valid {key} coordinate.", "corridors", name, "POSITION")

    directed = []
    for i, edge in enumerate(corridors.get("edges", [])):
        a, b = edge.get("from"), edge.get("to")
        if not isinstance(a, str) or not isinstance(b, str) or a not in names or b not in names:
            error(f"/corridors/edges/{i}", f"Edge endpoint not found: {a} → {b}.", "corridors", a if isinstance(a, str) else "", "REFERENCE")
            continue
        if str(names[a].get("floor")) != str(names[b].get("floor")):
            error(f"/corridors/edges/{i}", "Corridor edges cannot connect different floors; use a lift.", "corridors", a, "CROSS_FLOOR")
            continue
        directed.append((a, b, ""))
        if edge.get("bidirectional", True):
            directed.append((b, a, ""))
    directed += lift_pairs
    # Match the simulator's optional nearest-node connections for disconnected endpoints.
    if corridors.get("auto_connect", True) and not any(f.code == "POSITION" for f in findings):
        node_names = [n['name'] for n in corridors.get('nodes', []) if isinstance(n.get('name'), str)]
        outgoing = {a for a, _b, lift in directed if not lift}
        for name, point in names.items():
            if name in node_names or name in outgoing:
                continue
            candidates = [n for n in node_names if str(names[n].get("floor")) == str(point.get("floor"))]
            if candidates:
                near = min(candidates, key=lambda n: (float(point["x"]) - float(names[n]["x"])) ** 2 + (float(point["y"]) - float(names[n]["y"])) ** 2)
                directed.extend([(name, near, ""), (near, name, "")])

    # Repeated IDs may describe successive moves of one object, but its payload
    # type must agree. Do not reject legitimate sequential reuse as a duplicate.
    instance_types = {}
    for i, task in enumerate(config.get('tasks', [])):
        instance_id = str(task.get('payload_instance_id', '') or '').strip()
        payload = normalise_payload_name(task.get('payload', ''))
        recovery = task.get('recover_staged_payload', False)
        if not isinstance(recovery, bool):
            error(f'/tasks/{i}/recover_staged_payload', 'Recovery must be true or false.', 'tasks', task.get('id',''), 'RECOVERY_INPUT')
        elif recovery:
            if not instance_id or not payload:
                error(f'/tasks/{i}/payload_instance_id', 'Recovery needs a payload and the exact staged container ID.',
                      'tasks', task.get('id',''), 'RECOVERY_INPUT')
            if task.get('return_enabled') or task.get('requires_staff') or (task.get('dropoff_zone') and task.get('final_destination')):
                error(f'/tasks/{i}/recover_staged_payload', 'Recovery must be a direct task without a further return or staff handoff.',
                      'tasks', task.get('id',''), 'RECOVERY_INPUT')
            add('RECOVERY_POLICY', 'info', f'/tasks/{i}/recover_staged_payload', task.get('id',''),
                'This task collects only the named container marked as staged and requiring recovery at its pickup.',
                'It waits if that state is not reached; route, robot and destination capacity checks still apply. Unconfirmed arrivals cannot be recovered this way.',
                'Use the container identity and location from the run evidence; choose a release time and permitted route for a new run.',
                'tasks', task.get('id',''), kind='assumption')
        if not instance_id or not payload:
            continue
        previous = instance_types.setdefault(instance_id, payload)
        if previous != payload:
            error(f'/tasks/{i}/payload_instance_id',
                  f'Container {instance_id} is already declared as {previous}, not {payload}. '
                  'Use one payload type per physical container ID.',
                  'tasks', task.get('id', ''), 'PAYLOAD_ID_TYPE')

    profiles = config.get("route_profiles", {})
    for name, profile in profiles.items():
        for key, known in (("allowed_nodes", names), ("allowed_lifts", by_collection["lifts"])):
            value = profile.get(key, [])
            if not isinstance(value, list) or any(not isinstance(v, str) or v not in known for v in value):
                error(f"/route_profiles/{name}/{key}", f"{key} must list existing identifiers.", "route_profiles", name, "REFERENCE")
        pairs = profile.get("allowed_edges", [])
        if not isinstance(pairs, list) or any(not isinstance(p, (list, tuple)) or len(p) != 2 or any(not isinstance(n, str) or n not in names for n in p) for p in pairs):
            error(f"/route_profiles/{name}/allowed_edges", "Allowed edges must contain pairs of known node names.", "route_profiles", name, "REFERENCE")
    if profiles:
        add("PROFILE_POLICY", "info", "/route_profiles", "Route profile policy",
            "Shared sections are represented by allowing the same sections in each applicable profile.",
            "Empty lists are unrestricted and task allow-lists extend profile allowances. Profiles apply after pickup; "
            "empty approach, charging and idle-return journeys are unrestricted by profiles. A blank return profile "
            "uses the return task's label fallback, not automatic outbound-profile inheritance (seeded waste returns are an exception).",
            "Review profile overlap and set explicit return profiles where required.", "route_profiles", kind="assumption")

    def references(value, path="", section="project", target=""):
        if isinstance(value, dict):
            target = str(value.get("name", value.get("id", target)))
            for key, child in value.items():
                p = path + "/" + str(key)
                sec = section if path else str(key)
                known = profiles if key in {"route_profile", "return_route_profile"} else None
                if key in {"pickup", "dropoff", "pickup_location", "dropoff_location", "dropoff_zone", "final_destination"}:
                    known = by_collection["locations"]
                if key in {"payload", "return_payload"} and isinstance(child, str):
                    known = by_collection["payloads"] | {"__empty__"}
                if known is not None and child and (not isinstance(child, str) or child not in known):
                    if sec == 'task_generation' and isinstance(child, str):
                        add('GENERATION_REFERENCE', 'warning', p, target or p,
                            f'{key} references an unknown identifier: {child}.',
                            'This stored rule may be overridden by department settings; effective demand is not resolved by this check.',
                            'Review the rule and department assignments before relying on generated demand.', sec, target)
                    else:
                        error(p, f"{key} references an unknown identifier: {child}.", sec, target, "REFERENCE")
                if key in {'pickup_locations', 'dropoff_locations'}:
                    if not isinstance(child, list) or any(not isinstance(n, str) for n in child):
                        error(p, f'{key} must be a list of location names.', sec, target, 'REFERENCE')
                    else:
                        for n in child:
                            if n not in by_collection['locations']:
                                add('GENERATION_REFERENCE', 'warning', p, target or p,
                                    f'{key} includes unknown location: {n}.',
                                    'Inherited assignments may override this list; generated demand requires review.',
                                    'Review the rule and department assignments.', sec, target)
                references(child, p, sec, target)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                references(child, path + f"/{i}", section, target)

    references(config)
    for i, task in enumerate(config.get("tasks", [])):
        for key in ("pickup", "dropoff", "payload"):
            if not task.get(key):
                error(f"/tasks/{i}/{key}", f"Task requires {key}.", "tasks", task.get("id", ""), "REFERENCE")
        for key, known in (('allowed_nodes', names), ('allowed_lifts', by_collection['lifts'])):
            value = task.get(key, [])
            if not isinstance(value, list) or any(not isinstance(n, str) or n not in known for n in value):
                error(f'/tasks/{i}/{key}', f'{key} must list existing identifiers.', 'tasks', task.get('id', ''), 'REFERENCE')
        pairs = task.get('allowed_edges', [])
        if not isinstance(pairs, list) or any(not isinstance(p, (list, tuple)) or len(p) != 2 or any(not isinstance(n, str) or n not in names for n in p) for p in pairs):
            error(f'/tasks/{i}/allowed_edges', 'Allowed edges must contain pairs of known node names.', 'tasks', task.get('id', ''), 'REFERENCE')
        if not isinstance(task.get('labels', []), list):
            error(f'/tasks/{i}/labels', 'Task labels must be a list.', 'tasks', task.get('id', ''))
        elif not task.get('route_profile') and 'dirty' in task.get('labels', []) and 'dirty' not in profiles:
            error(f'/tasks/{i}/labels', "The dirty label selects route profile 'dirty', which does not exist.",
                  'tasks', task.get('id', ''), 'PROFILE_REFERENCE')
    completed_groups.add('references')
    # Deeper checks require structurally and numerically valid inputs.
    if any(f.severity == "error" for f in findings):
        add("CHECKS_INCOMPLETE", "info", "/", "Project", "Some dependent checks were skipped.",
            "Connectivity and compatibility cannot be assessed reliably until input errors are corrected.",
            "Correct errors and run checks again.", kind="coverage")
        return finish()

    # Resolve active demand rules without running a simulation. Generator setup
    # uses identifier membership only; physical objects are not needed here.
    from amr_sim_task_generation import TaskGenerationManager, SharedContainerConflictError
    from amr_sim_time_utils import SimulationClock
    try:
        TaskGenerationManager(copy.deepcopy(config), SimulationClock(dates['start_datetime']),
                              {key: None for key in by_collection['locations']},
                              {key: None for key in by_collection['payloads']}, prepare_runtime=False)
        completed_groups.add('shared_containers')
    except SharedContainerConflictError as exc:
        for message in exc.conflicts:
            error('/task_generation/categories/waste', message, 'task_generation', 'waste',
                  'SHARED_CONTAINER_CONFLICT')
        completed_groups.add('shared_containers')
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        error('/task_generation', f'Demand rules could not be resolved: {exc}', 'task_generation',
              code='GENERATION_RESOLUTION')

    def reachable(start, end, profile=None, task=None):
        profile, task = profile or {}, task or {}
        allowed_nodes = set(profile.get("allowed_nodes", [])) | set(task.get("allowed_nodes", []))
        allowed_lifts = set(profile.get("allowed_lifts", [])) | set(task.get("allowed_lifts", []))
        allowed_edges = {tuple(e) for e in profile.get("allowed_edges", [])} | {tuple(e) for e in task.get("allowed_edges", [])}
        if allowed_nodes and (start not in allowed_nodes or end not in allowed_nodes):
            return False
        adjacency = {}
        for a, b, lift in directed:
            if allowed_nodes and (a not in allowed_nodes or b not in allowed_nodes):
                continue
            if lift and allowed_lifts and lift not in allowed_lifts:
                continue
            if not lift and allowed_edges and (a, b) not in allowed_edges:
                continue
            adjacency.setdefault(a, set()).add(b)
        stack, seen = [start], set()
        while stack:
            node = stack.pop()
            if node == end:
                return True
            if node not in seen:
                seen.add(node)
                stack.extend(adjacency.get(node, set()) - seen)
        return False

    for i, task in enumerate(config.get("tasks", [])):
        profile = profiles.get(task.get("route_profile") or ("dirty" if "dirty" in task.get("labels", []) else ""), {})
        target = task.get("dropoff_zone") or task["dropoff"]
        try:
            connected = reachable(task["pickup"], target, profile, task)
        except (TypeError, ValueError):
            error(f"/tasks/{i}", "Task routing allowances must use identifier lists and edge pairs.", "tasks", task["id"])
            continue
        if not connected:
            add("TASK_UNREACHABLE", "warning", f"/tasks/{i}", task["id"],
                f"No directed graph route from {task['pickup']} to {target} under this task's allowances.",
                "This task is expected to fail even if a robot is available.",
                "Review connections or keep this warning for an intentional constraint study.", "tasks", task["id"])
    incident = {n for a, b, _lift in directed for n in (a, b)}
    for i, location in enumerate(config.get("locations", [])):
        if location["name"] not in incident and len(names) > 1:
            add("LOCATION_ISOLATED", "warning", f"/locations/{i}", location["name"],
                "Location has no corridor or lift connection.", "AMR journeys involving this location may be impossible.",
                "Connect it to the intended graph or acknowledge an intentional isolated location.", "locations", location["name"])

    completed_groups.add('graph')
    try:
        try:
            from .models import JsonStore, normalise_amr_payload_slots
        except ImportError:
            from models import JsonStore, normalise_amr_payload_slots
        for i, payload in enumerate(config.get("payloads", [])):
            compatible = False
            for amr in config.get("amrs", []):
                if int(amr.get("quantity", 1)) <= 0:
                    continue
                for slot in normalise_amr_payload_slots(copy.deepcopy(amr)):
                    from amr_robot_inputs import normalise_orientations
                    for orientation in normalise_orientations(payload.get("allowed_carry_orientations", ["lengthways", "sideways"])):
                        if orientation not in slot.get("allowed_payload_orientations", ["lengthways", "sideways"]):
                            continue
                        legacy_size = payload.get('size_units', 1)
                        length, width = float(payload.get("length_m", legacy_size)), float(payload.get("width_m", legacy_size))
                        if orientation == "sideways":
                            length, width = width, length
                        if (float(payload.get("weight_kg", 0)) <= float(slot.get("payload_capacity_kg", 0)) and
                            length <= float(slot.get("payload_length_capacity_m", 0)) and
                            width <= float(slot.get("payload_width_capacity_m", 0)) and
                            float(payload.get("height_m", legacy_size)) <= float(slot.get("payload_height_capacity_m", 0))):
                            compatible = True
            if not compatible:
                add("PAYLOAD_NO_AMR", "warning", f"/payloads/{i}", payload["name"],
                    "No configured active AMR slot can carry this payload.", "Tasks using it may fail for capacity or dimensions.",
                    "Review payload dimensions, allowed orientation and AMR capacity.", "payloads", payload["name"])
        completed_groups.add('compatibility')
        charge_plan = configured_fleet_bay_plan(config)
        completed_groups.add('charging')
        total, matched = len(charge_plan['robot_ids']), len(charge_plan['charger_assignment'])
        if charge_plan['explicit_bays'] and matched < total:
            add('CHARGE_START_CAPACITY', 'warning', '/building/charge_locations', 'Initial fleet',
                f'Only {matched} of {total} AMRs can occupy distinct compatible charger-equipped bays simultaneously.',
                'Remaining robots start in compatible parking bays or at the location point; this is not proof of sufficient physical parking or charging throughput.',
                'Review bay dimensions, type/instance restrictions and fleet size, or acknowledge the constrained start.', 'building')
        if charge_plan['legacy_locations']:
            add('CHARGE_LEGACY_LAYOUT', 'info', '/building/charge_locations', 'Legacy charging layout',
                'Location-level charging without AMR bays remains active at: ' + ', '.join(charge_plan['legacy_locations']),
                'Initial robots share a location point; distinct physical parking spaces have not been modelled.',
                'Add explicit AMR bays when testing physical storage capacity.', 'building')
        if include_legacy:
            for message in JsonStore(copy.deepcopy(config)).validate(include_charge_capacity=False):
                # Replace the older connectivity diagnostics with graph-aware findings above.
                if "not connected to the route graph" in message or "separate islands" in message or "not the corridor/lift graph" in message:
                    continue
                constraint = "requires" in message and "charger-equipped" in message
                add("LEGACY_CHECK", "warning" if constraint else "error", "/", "Existing validation", message,
                    "Review this existing validator finding before relying on a run.",
                    "Use the referenced settings to investigate.", "amrs" if constraint else "project")
            completed_groups.add('legacy')
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        error("/", f"Existing checks could not complete: {exc}", code="CHECK_FAILED")

    for section in ("floor_dxf_files", "floor_pdf_underlays"):
        for i, entry in enumerate(config.get(section, [])):
            value = entry.get("filepath", "")
            if value:
                if not isinstance(value, str):
                    error(f'/{section}/{i}/filepath', 'Drawing path must be text.', section)
                    continue
                path = Path(value)
                if not path.is_absolute() and base_path:
                    path = Path(base_path) / path
                if not path.is_file():
                    add("DRAWING_MISSING", "warning", f"/{section}/{i}/filepath", f"Floor {entry.get('floor', '?')}",
                        f"Drawing is unavailable: {value}", "The background cannot be displayed; explicit graph routes can still be simulated.",
                        "Relink the drawing or acknowledge a run without it.", section)
    completed_groups.add('drawings')
    from amr_payload_inputs import inventory_space_dimensions
    from amr_inventory_inputs import inventory_space_is_amr
    from amr_department_inputs import department_reference_findings, department_location_reference_findings
    for path, name in department_location_reference_findings(config):
        error(path, f'Unknown department service or drop-off-zone location {name!r}; resolve this assignment.', 'departments', code='DEPARTMENT_LOCATION_REFERENCE')
    for path, identity in department_reference_findings(config):
        add('DEPARTMENT_REFERENCE', 'warning', path, identity,
            f'No department matches {identity!r}; this assignment generates no department work.',
            'Other valid assignments may still generate tasks. This can be an intentional future rule.',
            'Choose an existing department identity, remove the assignment, or acknowledge the incomplete scenario.', 'task_generation')
    graph_names = {row['name'] for row in config.get('locations', [])}
    graph_names.update(row['name'] for row in config.get('corridors', {}).get('nodes', []))
    for lift in config.get('lifts', []):
        graph_names.update(f"{lift['id']}-F{floor}" for floor in lift.get('floor_locations', {}))
    for index, department in enumerate(config.get('departments', [])):
        if department.get('name') in graph_names:
            error(f'/departments/{index}/name', 'Department name conflicts with a graph point; rename the department before running. The graph point remains visible in the editor.', 'departments', code='DEPARTMENT_NAME_COLLISION')
        if any(float(department.get(key, 0)) for key in ('bed_count', 'staff_count', 'patient_turnover')):
            add('DEPARTMENT_DEMAND_SCOPE', 'info', f'/departments/{index}', department.get('name', department.get('id', '')),
                'Bed, staff and turnover values feed the legacy department-waste coefficient formula.',
                'They do not automatically set modern category demand or staff-service capacity.',
                'Configure category demand rates and staffing explicitly; calibrate waste coefficients against measured data.', 'departments', kind='unsupported')
    payload_definitions = {row['name']: row for row in config.get('payloads', [])}
    for index, location in enumerate(config.get('locations', [])):
        if location.get('bounding_box'):
            add('LOCATION_OUTLINE_SCOPE', 'info', f'/locations/{index}/bounding_box', location.get('name', ''),
                'Location outlines guide drawing, storage arrangement and reported plan measurements; they are not simulation walls.',
                'The simulator does not enforce room containment or swept clearance. Storage arrangement uses the outline envelope, which may extend outside a concave outline. Short or self-intersecting outlines are not verified room polygons.',
                'Use explicit graph restrictions and inventory bays for supported constraints; verify physical geometry separately.', 'locations', kind='unsupported')
        if location.get('people_area_type', '').strip().lower() not in {'', 'none'}:
            add('LOCATION_MODEL_SCOPE', 'info', f'/locations/{index}/people_area_type', location.get('name', ''),
                'Location people-area classification is stored metadata; current people routing checks corridor-edge classifications.',
                'This location setting does not restrict AMR or people access.',
                'Configure corridor people-area settings and AMR route profiles for their respective routing rules.', 'locations', kind='unsupported')
        spaces = location.get('inventory_spaces', [])
        if isinstance(spaces, list):
            for space_index, space in enumerate(spaces):
                bay_path = f'/locations/{index}/inventory_spaces/{space_index}'
                length, width, height = inventory_space_dimensions(space, payload_definitions, location)
                if length <= 0 or width <= 0:
                    add('INVENTORY_ENVELOPE', 'warning', bay_path, space.get('name', ''),
                        'The resolved bay has zero plan length or width; it cannot hold a normal positive-size payload or AMR.',
                        'Storage or charging may be unavailable at this bay.',
                        'Provide dimensions or a usable outline, or acknowledge the deliberately constrained bay.', 'locations')
                if height >= 999999:
                    add('INVENTORY_HEIGHT_SCOPE', 'warning', bay_path + '/height_m', space.get('name', ''),
                        'This bay uses an effectively unbounded height (999999 m or greater).',
                        'Vertical clearance is not established by this bay definition.',
                        'Set the actual height, use a known payload template, or acknowledge this legacy approximation.', 'locations')
                if inventory_space_is_amr(space) and any(slot.get('payload') for slot in space.get('payload_slots', [])):
                    add('INVENTORY_CLASSIFICATION', 'warning', bay_path, space.get('name', ''),
                        'AMR markers take precedence: this is an AMR-only bay despite its payload templates.',
                        'Payloads cannot be stored here. Payload templates can still contribute inferred height.',
                        'Use separate payload and AMR bays, or acknowledge the legacy mixed definition.', 'locations')
                if space.get('has_charger') and not inventory_space_is_amr(space):
                    add('INVENTORY_CHARGER_SCOPE', 'warning', bay_path + '/has_charger', space.get('name', ''),
                        'The charger flag on this payload bay does not add an AMR charging bay.',
                        'Only AMR bays supply bay-level chargers; legacy location-level charging may still apply.',
                        'Mark the bay as AMR storage if intended, or remove the unused charger flag.', 'locations')
                if isinstance(space, dict) and space.get('occupied'):
                    add('INVENTORY_OCCUPANCY_SCOPE', 'info', f'/locations/{index}/inventory_spaces/{space_index}/occupied',
                        space.get('name', ''), 'Initial bay occupancy is a blocking marker, not an initial physical-stock declaration.',
                        'The marker alone does not add payload instances or storage volume; AMR allocation can clear stale robot occupancy.',
                        'Use the supported stock-generation rules to initialise physical stock and review blocked bays.', 'locations')
                if isinstance(space, dict) and 'capacity_volume_m3' in space:
                    add('STORAGE_MODEL_SCOPE', 'info', f'/locations/{index}/inventory_spaces/{space_index}/capacity_volume_m3',
                        space.get('name', ''), 'Inventory capacity_volume_m3 is unused; fit uses the bay envelope and each bay holds one payload instance.',
                        'This field does not implement volumetric packing or additional payload capacity.',
                        'Set explicit bay dimensions and model separate bays where required.', 'locations', kind='unsupported')
    for index, payload in enumerate(config.get('payloads', [])):
        if 'volume_m3' in payload:
            add('PAYLOAD_MODEL_SCOPE', 'info', f'/payloads/{index}/volume_m3', payload.get('name', ''),
                'Payload volume_m3 is unused by physical fit and storage-volume accounting; those use resolved length × width × height.',
                'This metadata cannot replace dimensions or configure waste-stream capacity.',
                'Review physical dimensions and configure waste demand separately.', 'payloads', kind='unsupported')
    for index, robot in enumerate(config.get('amrs', [])):
        for field, message in (
                ('start_location', 'Per-type start_location is ignored; initial robots use configured compatible charging spaces.'),
                ('weight_kg', 'Robot weight is report metadata; robot own mass is not included in the current lift energy equation.')):
            if field in robot:
                add('ROBOT_MODEL_SCOPE', 'info', f'/amrs/{index}/{field}', robot.get('id', ''), message,
                    'This field does not change the stated simulation behaviour.',
                    'Review the robot and energy model contracts.', 'amrs', kind='unsupported')
        if 'manual_task_compatible' in robot and robot['manual_task_compatible'] != (len(normalise_amr_payload_slots(robot)) == 1):
            add('ROBOT_MODEL_SCOPE', 'info', f'/amrs/{index}/manual_task_compatible', robot.get('id', ''),
                'Manual-task compatibility metadata is derived from having exactly one payload slot; an explicit value does not override it.',
                'Import and simulation recompute this metadata.', 'Review the slot definition.', 'amrs', kind='assumption')
    add("MODEL_SCOPE", "info", "/corridors", "Movement model", "Lane capacity and turn drawings remain approximations.",
        "This check does not verify keep-right lane geometry, swept turns or physical contamination control.",
        "Consult the verification feature inventory before making physical clearance claims.", "corridors", kind="assumption")
    if config.get("lifts"):
        height = float(config.get('building', {}).get('floor_height_m', 4.0))
        for index, lift in enumerate(config['lifts']):
            if 'capacity_size_units' in lift:
                add('LIFT_LEGACY_CAPACITY', 'info', f'/lifts/{index}/capacity_size_units', lift.get('id', ''),
                    'Legacy size-unit capacity is unused. Cabin fit uses length, width and height.',
                    'This field cannot permit additional independent robots in a lift; reservations are exclusive.',
                    'Set physical cabin dimensions and review the model scope.', 'lifts', kind='unsupported')
            if 'speed_m_per_sec' in lift and not math.isclose(
                    float(lift['speed_m_per_sec']), float(lift['speed_floors_per_sec']) * height,
                    rel_tol=1e-9, abs_tol=1e-9):
                add('LIFT_SPEED_METADATA', 'warning', f'/lifts/{index}/speed_m_per_sec', lift.get('id', ''),
                    'Stored metres/second differs from the effective floors/second speed multiplied by floor height.',
                    'Simulation and lift displays use floors/second. Legacy rounded or stale speed metadata is not authoritative.',
                    'Review the effective speed and save the lift settings to synchronise its metadata, or acknowledge the difference.',
                    'lifts', kind='assumption')
        add("LIFT_MODEL_SCOPE", "info", "/lifts", "Lift scheduling",
            "Lifts with wear or failure thresholds serve booked journeys in commitment order.",
            "Earlier gaps are used only with wear and failures disabled and when the recorded journey preserves the next booking's starting floor. "
            "Failures use a deterministic operating-time threshold; repairs do not restore health. "
            "Scenario speed is sampled at phase entry; mid-journey outages are not simulated.",
            "Review lift settings and the lift reservation and repair references before interpreting reliability or utilisation.",
            "lifts", kind="assumption")
    completed_groups.add('scope')
    return finish()
