"""Fixed-roster human transport; shares the authoritative demand/stock lifecycle."""
from copy import deepcopy, copy
from dataclasses import asdict
import heapq
import math

from simulator import Simulation
from amr_contingency_inputs import service_of, peak_people, shift_candidates
from amr_contingency_routing import HumanRouter, NoHumanRoute
from amr_simulation_inputs import simulation_horizon_seconds
from amr_sim_models import Task


class StudyCancelled(Exception):
    pass


class HumanSimulation(Simulation):
    def __init__(self, config, settings, roster, buffered=False, cancelled=lambda:False):
        self.human_settings = deepcopy(settings)
        self.human_tasks = {}
        self.human_done = {}
        self.human_errors = {}
        self.human_rounds = []
        self.human_stops = []
        self.human_assigned = set()
        self.human_cancelled = cancelled
        self.human_factor = 1+settings['buffer_percent']/100 if buffered else 1.0
        self.human_roster = [dict(deepcopy(r), id=f'P{i+1}', available=r['start']) for i,r in enumerate(roster)]
        self.human_cutoff = max(c['end'] for c in shift_candidates(config, settings, 'shared'))
        self.human_horizon = simulation_horizon_seconds(config)
        runtime = deepcopy(config)
        runtime.pop('human_contingency', None)
        from amr_inventory_inputs import validate_inventory_inputs
        validate_inventory_inputs(config, check_references=True)
        robot_types = {r['id'] for r in runtime.get('amrs', [])}
        for location in runtime.get('locations', []):
            for space in location.get('inventory_spaces', []):
                for item in [space, *space.get('payload_slots', [])]:
                    for key in ('amr_type', 'amr'):
                        value = item.get(key, '')
                        base, _, suffix = value.rpartition('-')
                        if value not in robot_types and base in robot_types and suffix.isdecimal():
                            item[key] = base
        # Keep type definitions for inventory references; instantiate no robots.
        for robot in runtime.get('amrs', []):
            robot['quantity'] = 0
        runtime.setdefault('simulation', {}).update(mode='simple', motion_model='legacy',
            precompute_static_routes=False, enable_opportunity_charging=False)
        runtime.setdefault('building', {})['enable_idle_return'] = False
        # Use the complete native generation configuration, including disabled
        # rules, legacy waste precedence, calendars and initial stock ownership.
        # Select the study's services at the transport boundary, not at generation.
        super().__init__(runtime)
        self.human_router = HumanRouter(self)
        for person in self.human_roster:
            for time in [person['start'], person['end'], *[v for pair in person['breaks'] for v in pair]]:
                self.push_event(time, 'human_wake', {})
        self.push_event(self.human_horizon, 'human_wake', {})

    def _try_assign_tasks(self, now, force_idle_return=False):
        # The native dispatcher is deliberately never used for people.
        pass

    def _human_prepare(self, task):
        if getattr(task, '_human_prepared', False):
            return
        task._human_prepared = True
        task._human_service = service_of(task)
        if task._human_service not in self.human_settings['services']:
            return
        profile = self.human_settings['profiles'][task._human_service]
        task._human_handling = (0.0 if task.is_return_task or task.staff_handoff_only else
                               (task.staff_handling_minutes or profile['handling_minutes'])*60)
        task._human_deadline = task.release_time+task.target_time if task.target_time > 0 else self.human_cutoff
        if getattr(task, 'timeframe_deadline_time', 0) > 0:
            task._human_deadline = min(task._human_deadline, task.timeframe_deadline_time)
        task._human_original_zone = task.dropoff_zone
        if task.final_destination:
            task.dropoff = task.final_destination
            task.assigned_inventory_space = ''
        task.dropoff_zone = ''
        task.requires_staff = False
        task.staff_department_fallback_enabled = False
        self.human_tasks[task.id] = task

    def schedule_task_release(self, task):
        self._human_prepare(task)
        if task._human_service in self.human_settings['services']:
            super().schedule_task_release(task)

    def _queue_pending_task(self, task):
        self._human_prepare(task)
        if task._human_service in self.human_settings['services']:
            return super()._queue_pending_task(task)

    def _schedule_generated_task_record(self, record, release_time_override=None):
        if service_of(record.task) not in self.human_settings['services']:
            # Native staggering counts all generated records. Omitting another
            # service must not pull the selected service's scheduled work earlier.
            if not getattr(record, 'released_from_deferral', False):
                self._stagger_generated_task_release(record.task)
            return
        if not hasattr(record.task, '_human_return_target'):
            for generator in self.task_generation_manager.generators:
                for instance in getattr(generator, 'instances', []):
                    if instance['key'] == record.rule_id:
                        cfg = instance['cfg']
                        record.task._human_return_target = float(cfg.get('return_target_time', cfg.get('target_time', 0)) or 0)
        super()._schedule_generated_task_record(record, release_time_override=release_time_override)
        # Ordinary tasks are prepared by schedule_task_release after native
        # staggering. Deferred tasks also remain visible as unmet obligations;
        # their original deadline stays fixed when the dependency releases them.
        self._human_prepare(record.task)

    def _fail_task(self, task, reason, now=None):
        reason = str(reason).replace('without an AMR assignment', 'without a human assignment')
        self.human_errors[task.id] = reason
        return super()._fail_task(task, reason, now=now)

    def _schedule_configured_return_task(self, task, finish_time, amr_id=''):
        # Handling is already staffed. The passive dwell overlaps that handling.
        delay = task.return_delay_minutes
        task.return_delay_minutes = max(0.0, delay-task._human_handling*self.human_factor/60)
        before = set(self.human_tasks)
        try:
            super()._schedule_configured_return_task(task, finish_time, '')
        finally:
            task.return_delay_minutes = delay
        for name in set(self.human_tasks)-before:
            returned = self.human_tasks[name]
            returned._human_service = task._human_service
            returned.target_time = getattr(task, '_human_return_target', 0.0)
            returned._human_deadline = (returned.release_time+returned.target_time if returned.target_time > 0 else self.human_cutoff)
            # Exchanges return the previous container, not the newly delivered one.
            if self._task_is_staff_payload_exchange(task) and task.exchange_mode != 'top_up_only':
                candidates = [r for r in self.payload_instance_store.records_at(returned.pickup)
                              if r.payload == returned.payload and r.instance_id != task.payload_instance_id
                              and not self.payload_instance_store.is_reserved(r.instance_id)]
                returned.payload_instance_id = candidates[0].instance_id if candidates else ''
                returned.requires_existing_payload_instance = True
                returned.creates_new_payload_instance = False
            elif not (getattr(task, 'return_same_payload_instance', False) or
                      getattr(task, 'exchange_empty_payload_instance_id', '')):
                returned.requires_existing_payload_instance = True
                returned.creates_new_payload_instance = False
                if returned.payload != task.payload:
                    returned.payload_instance_id = ''

    def _fit(self, onboard, profile):
        if any(t.payload not in self.payloads for t in onboard):
            return False
        if sum(max(1, int(t.quantity)) for t in onboard) > profile['capacity_count']:
            return False
        if sum(self.payloads[t.payload].weight_kg*max(1, int(t.quantity)) for t in onboard) > profile['capacity_kg']+1e-9:
            return False
        for t in onboard:
            p = self.payloads[t.payload]
            if t.payload not in profile['payloads'] or p.height_m > profile['height_m']+1e-9:
                return False
            if not any((p.width_m <= profile['width_m'] and p.length_m <= profile['length_m']) if o == 'lengthways'
                       else (p.length_m <= profile['width_m'] and p.width_m <= profile['length_m'])
                       for o in p.allowed_carry_orientations):
                return False
        return True

    def _plan(self, person, sequence, now):
        if self.human_cancelled():
            raise StudyCancelled()
        tasks = list({t.id:t for _,t in sequence}.values())
        service = tasks[0]._human_service
        profile = self.human_settings['profiles'][service]
        if not self._plan_payload_claims(tasks, reserve=False):
            raise ValueError('Payload stock unavailable or already assigned.')
        current, time, onboard = person['base'], now, []
        bookings = self.human_router.bookings
        legs, actions = [], []
        swaps, swap_returns, used_instances = {}, [], set()
        washing = []
        wash_preview = copy(self)
        wash_preview.location_reservations = deepcopy(self.location_reservations)
        wash_preview.location_reservation_max_duration = dict(self.location_reservation_max_duration)
        def travel(destination):
            nonlocal time, current, bookings
            time, new, bookings = self.human_router.route(current, destination, time, profile, onboard,
                                                          self.human_factor, bookings)
            legs.extend(new)
            current = destination
        for action, task in sequence:
            target = task.pickup if action == 'pickup' else task.dropoff
            travel(target)
            if action == 'pickup':
                if task in onboard:
                    raise ValueError('Duplicate pickup.')
                onboard.append(task)
                if not self._fit(onboard, profile):
                    raise ValueError('Carrying capacity or permitted payload limit exceeded.')
                duration = profile['pickup_seconds']*max(1, task.quantity)*self.human_factor
            else:
                if task not in onboard:
                    raise ValueError('Delivery before pickup.')
                duration = (profile['unload_seconds']*max(1, task.quantity)+task._human_handling)*self.human_factor
                onboard.remove(task)
            start = time
            time += duration
            legs.append(dict(action=action, start=start, end=time, origin=current, destination=current,
                             distance_m=0.0, wait_seconds=0.0, task_id=task.id))
            actions.append((action, task, time))
            if action == 'deliver' and time > task._human_deadline+1e-7:
                raise ValueError('Delivery deadline cannot be met with this route and shift.')
            if action == 'deliver':
                # A full-for-empty handover can collect the previous physical
                # container immediately. Plan it as a real load on this round,
                # freeing the department bay atomically at the handover.
                immediate_exchange = (task.return_enabled and self._task_is_staff_payload_exchange(task)
                    and task.exchange_mode != 'top_up_only' and
                    (task.staff_handoff_only or task.return_delay_minutes*60 <= task._human_handling*self.human_factor))
                if immediate_exchange:
                    previous = next((r for r in self.payload_instance_store.records_at(task.dropoff)
                        if r.payload == (task.return_payload or task.payload) and r.instance_id != task.payload_instance_id
                        and r.instance_id not in used_instances and not self.payload_instance_store.is_reserved(r.instance_id)), None)
                    if previous is None:
                        raise ValueError('No previous physical container available for the department exchange.')
                    returned = Task('HUMAN-RETURN-'+task.id, task.dropoff, task.pickup, previous.payload,
                        release_time=time, target_time=getattr(task,'_human_return_target',0.0),
                        payload_instance_id=previous.instance_id, is_return_task=True, requires_staff=False,
                        route_profile=task.return_route_profile or None, labels=list(task.labels)+['return'])
                    returned.requires_existing_payload_instance=True
                    returned.creates_new_payload_instance=False
                    returned._human_prepared=True;returned._human_service=service;returned._human_handling=0.0
                    returned._human_deadline=time+returned.target_time if returned.target_time>0 else self.human_cutoff
                    returned.generator_collection_task_id=task.id
                    returned.generator_release_spacing_key=task.generator_release_spacing_key
                    returned.release_next_after_return_pickup=task.release_next_after_return_pickup
                    swaps[task.id]=returned;swap_returns.append(returned);tasks.append(returned)
                    used_instances.add(previous.instance_id);onboard.append(returned)
                    if not self._fit(onboard,profile):
                        raise ValueError('Carrying capacity exceeded by collected exchange containers.')
                    start=time;time+=profile['pickup_seconds']*self.human_factor
                    legs.append(dict(action='exchange_pickup',start=start,end=time,origin=current,destination=current,
                        distance_m=0.0,wait_seconds=0.0,task_id=returned.id))
                trigger = next((loc for loc in (self.locations[task.dropoff], self.locations[task.pickup])
                                if loc.wash_cycle_required), None)
                if trigger:
                    travel(trigger.wash_location or task.dropoff)
                    duration = trigger.wash_cycle_duration_sec
                    ready = wash_preview._find_next_available_time(current, time, duration)
                    if ready > time:
                        legs.append(dict(action='wash_wait',start=time,end=ready,origin=current,destination=current,
                                         distance_m=0.0,wait_seconds=0.0,task_id=task.id))
                    wash_preview._reserve_location(current, ready, ready+duration)
                    washing.append((current,ready,ready+duration))
                    legs.append(dict(action='wash',start=ready,end=ready+duration,origin=current,destination=current,
                                     distance_m=0.0,wait_seconds=0.0,task_id=task.id))
                    time = ready+duration
        for returned in swap_returns:
            travel(returned.dropoff)
            start=time;time+=profile['unload_seconds']*self.human_factor
            onboard.remove(returned)
            if time>returned._human_deadline+1e-7:
                raise ValueError('Exchange return deadline cannot be met.')
            legs.append(dict(action='deliver',start=start,end=time,origin=current,destination=current,
                distance_m=0.0,wait_seconds=0.0,task_id=returned.id))
            actions.append(('deliver',returned,time))
        if onboard:
            raise ValueError('Round ends with undelivered payloads.')
        travel(profile['base'])
        if current != person['base']:
            travel(person['base'])
        if time > person['end']+1e-7 or any(now < b and time > a for a,b in person['breaks']):
            raise ValueError('Round overlaps a break or would require overtime.')
        return dict(service=service, start=now, end=time, tasks=tasks, legs=legs, actions=actions,
                    bookings=bookings, washing=washing, swaps=swaps, distance_m=sum(v['distance_m'] for v in legs))

    def dispatch(self, now):
        pending = [r[3] for r in self.pending_tasks if r[3].id not in self.human_assigned and r[3].id not in self.failed_task_ids]
        pending.sort(key=lambda t:(t._human_deadline, -t.priority, t.release_time, t.id))
        for person in self.human_roster:
            if not person['start'] <= now < person['end'] or now < person['available']-1e-7:
                continue
            if any(a <= now < b for a,b in person['breaks']):
                continue
            candidates = [t for t in pending if t.id not in self.human_assigned and
                          (person['pool'] == 'shared' or person['pool'] == t._human_service)]
            chosen, sequence = None, []
            for task in candidates:
                try:
                    sequence = [('pickup', task), ('deliver', task)]
                    chosen = self._plan(person, sequence, now)
                    break
                except ValueError as exc:
                    self.human_errors[task.id] = str(exc)
                    self._set_task_pending_reason(task, str(exc))
            if chosen is None:
                continue
            same = [t for t in candidates if t._human_service == chosen['service'] and t.id != chosen['tasks'][0].id]
            for task in same[:self.human_settings['max_round_tasks']-1]:
                best = None
                for i in range(len(sequence)+1):
                    for j in range(i+1, len(sequence)+2):
                        trial = sequence[:]
                        trial.insert(i, ('pickup', task)); trial.insert(j, ('deliver', task))
                        try:
                            plan = self._plan(person, trial, now)
                            key = (plan['end'], plan['distance_m'])
                            if best is None or key < best[0]:
                                best = (key, plan, trial)
                        except ValueError:
                            continue
                if best:
                    _, chosen, sequence = best
            if not self._plan_payload_claims(chosen['tasks'], reserve=True):
                continue
            self.human_router.commit(chosen['bookings'])
            for location,start,end in chosen['washing']:
                self._reserve_location(location,start,end)
            person['available'] = chosen['end']
            round_id = f'ROUND-{len(self.human_rounds)+1}'
            task_ids = [t.id for t in chosen['tasks']]
            self.human_assigned.update(task_ids)
            for task_id in task_ids:
                self._task_deferrals.pop(task_id, None)
            for task in chosen['swaps'].values():
                self.human_tasks[task.id]=task
            self.pending_tasks = [r for r in self.pending_tasks if r[3].id not in task_ids]
            heapq.heapify(self.pending_tasks)
            self.human_rounds.append(dict(id=round_id, person=person['id'], service=chosen['service'],
                start=now, end=chosen['end'], tasks=task_ids, distance_m=chosen['distance_m']))
            for leg in chosen['legs']:
                self.human_stops.append(dict(leg, person=person['id'], round=round_id, service=chosen['service'], tasks=task_ids))
            for action, task, time in chosen['actions']:
                self.push_event(time, 'human_'+action, dict(task=task, person=person['id'], round=round_id,
                    swap_task=chosen['swaps'].get(task.id) if action=='deliver' else None))
            self.push_event(chosen['end'], 'human_wake', {})

    def handle_human(self, event):
        task = event.payload['task']
        if task.id in self.failed_task_ids:
            return
        try:
            if event.event_type == 'human_pickup':
                self._process_payload_pickup(task, self._payload_for_task(task), event.time)
                if task.is_return_task:
                    self._notify_task_generation_state(task, 'return_payload_picked_up', event_time=event.time)
            else:
                swap = event.payload.get('swap_task')
                if swap is not None:
                    self._process_payload_pickup(swap,self._payload_for_task(swap),event.time)
                self._process_payload_dropoff(task, self._payload_for_task(task), event.time)
                self.human_done[task.id] = event.time
                if swap is None:
                    self._schedule_configured_return_task(task, event.time)
                self._notify_task_generation_state(task, 'completed', event_time=event.time)
                if swap is not None:
                    self._notify_task_generation_state(swap,'return_payload_picked_up',event_time=event.time)
        except (RuntimeError, ValueError) as exc:
            self.human_errors[task.id] = str(exc)
            self._fail_task(task, str(exc), now=event.time)
            if event.payload.get('swap_task') is not None:
                self._fail_task(event.payload['swap_task'],str(exc),now=event.time)

    def evaluate(self):
        try:
            while self.events:
                if self.human_cancelled():
                    raise StudyCancelled()
                now = self.events[0].time
                if now > self.human_cutoff:
                    break
                self.current_time = max(self.current_time, now)
                while self.events and self.events[0].time <= now+1e-9:
                    event = heapq.heappop(self.events)
                    self._mark_task_activity_changed()
                    if event.event_type in ('human_pickup', 'human_deliver'):
                        self.handle_human(event)
                    elif event.event_type != 'human_wake':
                        super()._handle_event(event)
                self.dispatch(self.current_time)
            return self.result()
        finally:
            if self.routing_executor is not None:
                self.routing_executor.shutdown(wait=True)
            if self.event_store is not None and not self.event_store.closed:
                self.event_store.close()

    def result(self):
        unresolved = []
        for task in self.human_tasks.values():
            finish = self.human_done.get(task.id)
            if finish is None or finish > task._human_deadline+1e-7:
                unresolved.append(dict(task=task.id, service=task._human_service, release=task.release_time,
                    deadline=task._human_deadline, reason=self.human_errors.get(task.id,
                    'Insufficient staffing or no eligible shift covering the work.')))
        balances = dict(tracked=self.task_generation_manager.tracked_item_balance(),
                        waste=self.task_generation_manager.waste_volume_balance(),
                        direct=self.task_generation_manager.direct_volume_balance())
        selected_rules = {instance['key'] for generator in self.task_generation_manager.generators
                          for instance in getattr(generator, 'instances', [])
                          if instance['category_key'] in self.human_settings['services']}
        for kind, rows in balances.items():
            balances[kind] = [row for row in rows if
                row.get('rule_id', row.get('group', '')) in selected_rules or
                ('waste' in self.human_settings['services'] and
                 str(row.get('rule_id', row.get('group', ''))).startswith('legacy_waste:'))]
        for row in balances['tracked']:
            if row.get('unmet', 0) > 1e-7:
                unresolved.append(dict(task=row['rule_id'], service='stock', release=0,
                    deadline=self.human_horizon, reason='Tracked stock consumption was not fulfilled.'))
        tasks = [dict(id=t.id, service=t._human_service, pickup=t.pickup, dropoff=t.dropoff, payload=t.payload,
            payload_instance_id=t.payload_instance_id, release=t.release_time, deadline=t._human_deadline,
            completed=self.human_done.get(t.id), is_return=t.is_return_task) for t in self.human_tasks.values()]
        totals = {kind:sum((s['end']-s['start']) for s in self.human_stops if s['action'] == kind)
                  for kind in ('walk', 'lift', 'pickup', 'exchange_pickup', 'deliver', 'wash', 'wash_wait')}
        by_service = {name:dict(active_hours=sum(s['end']-s['start'] for s in self.human_stops if s['service']==name)/3600,
                               trips=sum(r['service']==name for r in self.human_rounds),
                               completed=sum(t['service']==name and t['completed'] is not None for t in tasks))
                      for name in self.human_settings['services']}
        return dict(passed=bool(tasks) and not unresolved, obligations=len(tasks), completed=len(self.human_done),
            services=by_service,
            unresolved=unresolved, roster=[{k:v for k,v in p.items() if k != 'available'} for p in self.human_roster],
            peak_people=peak_people(self.human_roster),
            staffed_hours=sum(p['end']-p['start'] for p in self.human_roster)/3600,
            break_hours=sum(b-a for p in self.human_roster for a,b in p['breaks'])/3600,
            active_hours=sum(totals.values())/3600, walking_hours=totals['walk']/3600,
            handling_hours=(totals['pickup']+totals['exchange_pickup']+totals['deliver'])/3600,
            lift_hours=totals['lift']/3600, lift_wait_hours=sum(s['wait_seconds'] for s in self.human_stops)/3600,
            washing_hours=(totals['wash']+totals['wash_wait'])/3600,
            trips=len(self.human_rounds), distance_m=sum(r['distance_m'] for r in self.human_rounds),
            rounds=self.human_rounds, stops=self.human_stops, tasks=tasks, balances=balances,
            inventory=[asdict(r) for r in self.payload_instance_store._known_instances.values()])


def simulate_candidate(config, settings, roster, *, buffered=False, cancelled=lambda:False):
    return HumanSimulation(config, settings, roster, buffered, cancelled).evaluate()
