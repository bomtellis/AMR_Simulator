"""Explicit queue snapshots at a run stop; never infer failure from waiting."""

CAPABILITY = 'pending_tasks_at_stop_v1'


def record_pending_at_stop(simulation):
    pending = {task.id: task for _, _, _, task in simulation.pending_tasks
               if not simulation._pending_task_removed(task)}
    simulation._evidence_pending_task_ids = sorted(pending)
    if CAPABILITY not in simulation._evidence_event_capabilities:
        simulation._evidence_event_capabilities.append(CAPABILITY)
    for task_id, task in sorted(pending.items()):
        last_reason = str(getattr(task, 'pending_reason', '') or '').strip()
        reason = ('Last recorded candidate reason: ' + last_reason if last_reason else
                  'No candidate-specific reason was recorded.')
        simulation.log_step(
            event_time=simulation.current_time, event_type='task_pending_at_stop',
            task_id=task_id, payload_name=task.payload,
            from_location=task.pickup, to_location=task.dropoff,
            status='pending at stop', pending_reason=reason,
            details=f'Run status: {simulation._evidence_run_status}. '
                    f'Scheduled events remaining: {len(simulation.events)}. '
                    'Task remained in the pending queue; this is not a failure outcome. ' + reason,
        )
