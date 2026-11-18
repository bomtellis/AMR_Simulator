"""Structured observations from the dispatcher and resource ledgers."""
import json


CAPABILITY = 'failure_investigation_v1'


def blocker_from_reason(reason):
    text = (reason or '').casefold().split('last_pending_reason=')[-1]
    if 'spare empty bin' in text:
        return 'Spare bin'
    if 'inventory space' in text or 'compatible bay' in text:
        return 'Inventory bays'
    if 'return pickup' in text:
        return 'Return pickup'
    if 'available at pickup location' in text or 'available at' in text and 'for exchange' in text:
        return 'Pickup stock'
    if 'battery' in text or 'charg' in text or 'energy' in text:
        return 'Battery or charging'
    if 'capacity' in text or 'weight/dimensions' in text:
        return 'AMR capacity'
    if 'route' in text or 'manoeuvre' in text or 'lift' in text or 'traffic' in text:
        return 'Route or lift'
    if 'deferral limit' in text or 'assignment' in text or 'amr availability' in text or 'reserved for' in text:
        return 'Dispatch'
    return 'Other or unknown'


def record(sim, task, kind, data, *, now=None, amr_id=''):
    return sim.log_step(event_time=sim.current_time if now is None else now,
        event_type=kind, task_id=task.id, amr_id=amr_id,
        details=json.dumps(data, ensure_ascii=False), from_location=task.pickup, to_location=task.dropoff,
        payload_name=sim._payload_log_name(task.payload), payload_instance_id=task.payload_instance_id,
        task_source=task.task_source, department_id=task.department_id, waste_stream=task.waste_stream)


def resource_state(sim, task, blocker):
    data = {}
    if blocker in ('Pickup stock', 'Spare bin'):
        records = [row for row in sim.payload_instance_store.records_at(task.pickup)
                   if row.payload == task.payload]
        if sim._uses_seeded_waste_bin(task):
            records = [row for row in records if sim._bin_matches_group(getattr(task, 'container_group', ''), row)]
        empty = [row for row in records if sim._record_is_available_empty_container(row)]
        owners = sim.payload_instance_store.reservation_owner
        data['stock'] = dict(location=task.pickup, matching=len(records), empty=len(empty),
                             available=sum(not owners(row.instance_id) for row in empty),
                             reserved=[dict(payload_id=row.instance_id, task_id=owners(row.instance_id))
                                       for row in empty if owners(row.instance_id)])
    if getattr(task, 'waste_bin_swap', False):
        key = sim._waste_bin_replacement_key(task)
        data['swap_key'] = list(key)
        data['spares'] = [dict(task_id=spare.id, payload_id=spare.payload_instance_id,
                              amr_id=getattr(spare, 'waste_replacement_amr_id', ''),
                              claimed_by=getattr(spare, 'waste_collection_id', ''),
                              staged=bool(getattr(spare, 'payload_dropoff_processed', False)))
                         for spare in sim._waste_bin_replacements.get(key, ())]
    if blocker == 'Inventory bays':
        payload = sim._payload_for_task(task)
        spaces = sim.inventory_spaces_by_location.get(task.dropoff, ())
        compatible = [space for space in spaces if payload and sim._inventory_space_can_fit_payload(space, payload)]
        data['bays'] = dict(location=task.dropoff, total=len(spaces), compatible=len(compatible),
            free=sum(not space.get('occupied') and not space.get('reserved_by_task') for space in compatible),
            occupied=sum(bool(space.get('occupied')) for space in compatible),
            reserved=sum(bool(space.get('reserved_by_task')) for space in compatible),
            holders=[dict(bay=space.get('name', ''), task_id=space.get('reserved_by_task') or space.get('task_id', ''),
                          payload_id=space.get('payload_instance_id', '')) for space in compatible
                     if space.get('occupied') or space.get('reserved_by_task')])
    return data


def blocker_changed(sim, task, blocker, reason=''):
    if not sim._record_failure_diagnostics:
        return
    previous = sim._investigation_blockers.get(task.id)
    if previous is None and blocker == 'Dispatch':
        return
    data = dict(blocker=blocker, reason=reason, **resource_state(sim, task, blocker))
    if data != previous:
        sim._investigation_blockers[task.id] = data
        record(sim, task, 'task_blocker_changed', data)


def terminal_snapshot(sim, task, reason, now, *, pending=False):
    if not sim._record_failure_diagnostics or task.id in sim.failed_task_ids:
        return
    previous = sim._investigation_blockers.pop(task.id, None)
    blocker = blocker_from_reason(reason)
    if blocker in ('Dispatch', 'Other or unknown') and previous:
        blocker = previous['blocker']
    deferral = sim._task_deferrals.get(task.id)
    data = dict(blocker=blocker, reason=reason, release=deferral[1] if deferral else task.release_time,
                deadline=deferral[2] if deferral else None, **resource_state(sim, task, blocker))
    outcomes = [dict(amr_id=amr, **{key: result[key] for key in ('reason', 'detail', 'blocking_owners') if key in result})
                for (amr, task_id), result in sim.geometric_candidate_outcomes.items() if task_id == task.id]
    if outcomes:
        data['route_candidates'] = outcomes
    payload = sim._payload_for_task(task)
    estimates = sim._investigation_estimates.pop(task.id, {})
    data['amr_candidates'] = [dict(
        amr_id=amr.id,
        payload_compatible=bool(payload and sim._amr_can_carry_payload(amr, payload)),
        dispatch_blocker=sim._amr_dispatch_blocker(task, amr),
        charging=bool(amr.is_charging), available_time=amr.available_time,
        battery_soc_percent=amr.battery_soc_percent,
        last_estimate=estimates.get(amr.id),
        waste_cycle_tasks=sorted(getattr(amr, 'waste_bin_task_ids', ())),
        exchange_tasks=dict(getattr(amr, 'exchange_tasks', {}))) for amr in sim.amrs]
    record(sim, task, 'task_pending_snapshot' if pending else 'task_failure_snapshot', data, now=now)


def dispatch_committed(sim, tasks, amr, plan, *, prior_available, spare=None):
    if not sim._record_failure_diagnostics:
        return
    previous = sim._investigation_amr_work.get(amr.id)
    if prior_available <= sim.current_time or previous and abs(previous['finish'] - prior_available) > 1e-6:
        previous = None
    for task in tasks:
        sim._investigation_blockers.pop(task.id, None)
        sim._investigation_estimates.pop(task.id, None)
        deadline = sim._task_deferrals.get(task.id)
        record(sim, task, 'task_dispatch_committed', dict(
            committed=sim.current_time, start=plan['task_start_time'], finish=plan['finish_time'],
            deadline=deadline[2] if deadline else None,
            amr_available=prior_available, previous_work=previous, spare_task_id=spare.id if spare else '',
            spare_payload_id=spare.payload_instance_id if spare else '',
            swap_key=list(sim._waste_bin_replacement_key(task)) if getattr(task, 'waste_bin_swap', False) else None,
            working_payload_id=task.payload_instance_id), amr_id=amr.id)
    sim._investigation_amr_work[amr.id] = dict(tasks=[task.id for task in tasks], finish=plan['finish_time'])
