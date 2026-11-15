"""Directed graph preflight for effective task definitions, without simulation."""
from collections import defaultdict


class RouteGraph:
    def __init__(self, points, directed, profiles, lift_stops=(), config=None):
        self.points = set(points)
        self.config = config or {}
        self.floors = {name: int(value['floor']) for name, value in points.items()} if isinstance(points, dict) else {}
        self.directed = directed
        self.profiles = profiles
        self.lift_stops = set(lift_stops) | {n for a, b, lift in directed if lift for n in (a, b)}
        for name in self.lift_stops:
            try:
                self.floors.setdefault(name, int(name.rsplit('-F', 1)[1]))
            except (IndexError, ValueError):
                pass
        self.cache = {}

    def rules(self, task):
        name = task.get('route_profile') or ('dirty' if 'dirty' in (task.get('labels') or []) else '')
        if name and name not in self.profiles:
            raise ValueError(f"Unknown route profile {name!r}.")
        profile = self.profiles.get(name, {})
        return name, tuple(frozenset(tuple(v) if key == 'allowed_edges' else v
                                   for v in (profile.get(key) or []) + (task.get(key) or []))
                           for key in ('allowed_nodes', 'allowed_edges', 'allowed_lifts'))

    def reached(self, start, rules, end=None, *, profile_applied=False):
        from amr_forced_floor import enabled
        if enabled(self.config):
            return self._forced_reached(start, rules, end, profile_applied)
        from amr_floor_routing import required_waypoint
        start_floor, end_floor = self.floors.get(start), self.floors.get(end)
        via = required_waypoint(self.config, start_floor, end_floor)
        transfer_floor = self.config.get('building', {}).get('lift_transfer_floor')
        key = start, rules, end, via, transfer_floor
        if key not in self.cache:
            nodes, edges, lifts = rules
            adjacency = defaultdict(set)
            transfers = defaultdict(set)
            for a, b, lift in self.directed:
                if nodes and not {a, b} <= nodes:
                    continue
                if lift:
                    if lifts and lift not in lifts:
                        continue
                    transfers[a].add(b)
                elif edges and (a, b) not in edges:
                    continue
                else:
                    adjacency[a].add(b)

            def same_floor(origin):
                seen = set()
                todo = [origin] if origin in self.points and (not nodes or origin in nodes) else []
                while todo:
                    node = todo.pop()
                    if node in seen:
                        continue
                    seen.add(node)
                    if node == origin or node not in self.lift_stops:
                        todo.extend(adjacency[node] - seen)
                return seen

            direct_reachable = any(
                self.floors.get(landing) == end_floor and end in same_floor(landing)
                for node in same_floor(start) for landing in transfers[node])
            effective_via = via if via is not None else (None if direct_reachable else transfer_floor)
            # Repeated lift journeys are allowed. Lift stops remain terminal
            # walking nodes until an actual lift ride has alighted there.
            seen = set()
            pending = [(start, effective_via is None or start_floor == effective_via, frozenset({start_floor}))]
            visited = set()
            while pending:
                origin, satisfied, used_floors = pending.pop()
                state = origin, satisfied, used_floors
                if state in visited:
                    continue
                visited.add(state)
                walking = same_floor(origin)
                if satisfied:
                    seen.update(walking)
                # Preserve the same-floor contract: lifts do not bypass gaps
                # in a floor's circulation graph for same-floor deliveries.
                if end_floor is not None and start_floor == end_floor:
                    continue
                for node in walking:
                    for landing in transfers[node]:
                        floor = self.floors.get(landing)
                        if floor not in used_floors:
                            pending.append((landing, satisfied or floor == effective_via, used_floors | {floor}))
            self.cache[key] = seen
        return self.cache[key]

    def _forced_reached(self, start, rules, end, profile_applied):
        """Structural graph audit, allowing repeated floors in distinct phases."""
        from amr_floor_routing import lift_policy_key
        from amr_forced_floor import lift_allowed_at_required_floor, lift_preference

        via = self.config['building']['force_via_floor']
        mode, selected = lift_preference(self.config, self.floors.get(start), profile_applied)
        if mode != 'required':
            selected = None
        key = ('forced', start, rules, end, lift_policy_key(self.config), profile_applied)
        if key in self.cache:
            return self.cache[key]
        nodes, edges, lifts = rules
        adjacency = defaultdict(list)
        for a, b, lift in self.directed:
            if nodes and not {a, b} <= nodes:
                continue
            if lift and lifts and lift not in lifts:
                continue
            if lift and not lift_allowed_at_required_floor(
                    lift, self.floors.get(a), self.floors.get(b), via, selected):
                continue
            if not lift and edges and (a, b) not in edges:
                continue
            adjacency[a].append((b, bool(lift)))
        satisfied = start == end or self.floors.get(start) == via
        local_only = start == end or self.floors.get(start) == self.floors.get(end) == via
        # Walking can arrive at a lift stop to board it, but cannot use its
        # interior as a corridor. An actual lift arrival may exit the stop.
        pending = [(start, satisfied, True)] if start in self.points and (not nodes or start in nodes) else []
        seen = set()
        reached = set()
        while pending:
            node, visited, may_exit = pending.pop()
            state = node, visited, may_exit
            if state in seen:
                continue
            seen.add(state)
            if visited:
                reached.add(node)
            for destination, ride in adjacency[node]:
                if ride and local_only:
                    continue
                if not ride and node in self.lift_stops and not may_exit:
                    continue
                satisfied = visited or ride and self.floors.get(destination) == via
                pending.append((destination, satisfied, ride or destination not in self.lift_stops))
        self.cache[key] = reached
        return reached

    def inspect(self, task, *, source, path, name, leg='Outbound', department=''):
        start = task['pickup']
        end = task.get('dropoff_zone') if task.get('dropoff_zone') and task.get('final_destination') else task['dropoff']
        profile = task.get('route_profile') or ('dirty' if 'dirty' in (task.get('labels') or []) else '')
        row = dict(source=source, path=path, name=name, department=department,
                   profile=profile or '', pickup=start, dropoff=end, leg=leg)
        try:
            profile, rules = self.rules(task)
            profile_applied = bool(profile)
            connected = end in self.reached(start, rules, end, profile_applied=profile_applied)
            if connected:
                reason = 'A directed graph path exists under the effective profile and task allowances.'
            elif start not in self.points or end not in self.points:
                reason = 'A route endpoint is missing from the graph.'
            elif end in self.reached(start, (frozenset(),) * 3, end, profile_applied=profile_applied):
                reason = 'The graph connects these locations, but node, edge or lift permissions block this route.'
            else:
                reason = 'No directed graph path connects these locations, even without profile restrictions.'
                if self.lift_stops:
                    reason += ' Lift stops cannot connect corridors on the same floor; a lift journey must change floors.'
            from amr_floor_routing import required_waypoint
            via = required_waypoint(self.config, self.floors.get(start), self.floors.get(end))
            from amr_forced_floor import enabled, lift_preference
            if enabled(self.config) and start != end:
                via = self.config['building']['force_via_floor']
            if via is not None:
                reason += f' Mandatory waypoint: floor {via}.'
                mode, selected = lift_preference(self.config, self.floors.get(start), profile_applied)
                if mode == 'required' and start != end:
                    reason += f' Rides into or out of floor {via} require one of: {", ".join(sorted(selected))}.'
            row.update(status='Reachable' if connected else 'Blocked', reason=reason)
        except ValueError as exc:
            if via := required_waypoint_for_end(self.config, self.floors, start, end):
                reason += f' Mandatory waypoint: floor {via[0]}.'
            row.update(status='Invalid', reason=str(exc))
        return row


def audit_task_routes(config, points, directed, generation_manager=None):
    """Audit every possible location pair of each enabled resolved demand rule.

    Counts are route definitions, not release counts. Runtime-dependent rules
    and returns are included without predicting whether/when they will release.
    """
    from amr_sim_task_generation import DynamicCategoryTaskGenerator, DepartmentWasteTaskGenerator
    if not isinstance(points, dict):
        floors = {v['name']: v for v in config.get('locations', []) + config.get('corridors', {}).get('nodes', [])}
        floors.update({f"{lift['id']}-F{floor}": {'floor': int(floor)}
                       for lift in config.get('lifts', []) for floor in lift.get('served_floors', [])})
        points = {name: floors[name] for name in points if name in floors}
    lift_stops = {f"{lift['id']}-F{floor}" for lift in config.get('lifts', [])
                  for floor in lift.get('floor_locations', {})}
    graph = RouteGraph(points, directed, config.get('route_profiles', {}), lift_stops, config)
    rows = []
    seeded_bins=bool(config.get('simulation',{}).get('seed_waste_stream_containers_at_start',False))

    def inspect(task, source, path, name, department='', mandatory_return=False, leg='Outbound'):
        rows.append(graph.inspect(task, source=source, path=path, name=name, department=department, leg=leg))
        if leg != 'Return' and (task.get('return_enabled') or mandatory_return):
            end = task.get('dropoff_zone') if task.get('dropoff_zone') and task.get('final_destination') else task['dropoff']
            # Runtime return tasks use their own profile and inherit labels,
            # rather than the outbound task's local permission extensions.
            return_task = dict(pickup=end, dropoff=task['pickup'], labels=task.get('labels') or [],
                               route_profile=task.get('return_route_profile') or
                               (task.get('route_profile') if mandatory_return else ''))
            rows.append(graph.inspect(return_task, source=source, path=path, name=name,
                                      leg='Return', department=department))

    for index, task in enumerate(config.get('tasks', [])):
        provenance=task.get('task_source') or ''
        generated=provenance.startswith('task_generation') or provenance in {'department_waste','dropoff_zone_staff_return'}
        inspect(task, 'Generated task' if generated else 'Manual task', f'/tasks/{index}',
                task['id'], task.get('department_id', ''),
                mandatory_return=seeded_bins and bool(task.get('waste_stream') or provenance=='department_waste') and task.get('initial_container_present',True),
                leg='Return' if task.get('is_return_task') else 'Outbound')
    for generator in getattr(generation_manager, 'generators', []):
        if isinstance(generator, DynamicCategoryTaskGenerator):
            for instance in generator.instances:
                cfg = instance['cfg']
                for pickup in dict.fromkeys(instance.get('pickup_locations', [])):
                    for dropoff in dict.fromkeys(instance.get('dropoff_locations', [])):
                        if pickup == dropoff:
                            continue
                        resolved = dict(instance)
                        final = next((value for value in instance.get('final_destination_locations', []) if value != dropoff), '')
                        if final:
                            resolved['_resolved_final_destination_by_pair'] = {(pickup, dropoff): final}
                        task = generator._base_task(resolved, pickup, dropoff, cfg.get('payload', ''), 0)
                        if task is None:
                            continue
                        mandatory = seeded_bins and bool(getattr(task, 'waste_stream', '') and getattr(task, 'initial_container_present', False))
                        inspect(vars(task), 'Generated rule', instance.get('rule_path') or '/task_generation',
                                instance['key'], instance.get('department_id', ''), mandatory)
        elif isinstance(generator, DepartmentWasteTaskGenerator):
            for instance in generator.container_instances():
                dept = instance['department']
                record = generator._create_task_record(dept, instance['waste_stream'], 0, 0)
                if record is None:
                    continue
                index = next(i for i, row in enumerate(config.get('departments', [])) if row == dept)
                inspect(vars(record.task), 'Legacy waste rule', f'/departments/{index}/waste',
                        instance['key'], instance['department_id'],
                        seeded_bins and instance['cfg'].get('initial_container_present', True))
    return rows
