"""Read recorded dynamic accumulated-waste balances; never reconstruct missing stock."""
import json
import math

FIELDS = ('accrued_m3', 'residual_m3', 'pending_m3', 'completed_m3', 'unconfirmed_m3',
          'restored_after_failure_m3')
STATUS_FIELDS = {'pending': 'pending_m3', 'completed': 'completed_m3',
                 'unconfirmed': 'unconfirmed_m3', 'restored': 'restored_after_failure_m3'}


def summarize_waste_volume(events, *, complete, capabilities):
    result = {'known': False, 'matches': None, 'totals': {key: None for key in FIELDS},
              'groups': [], 'event_ids': [], 'issues': []}
    snapshots = [event for event in events if event['type'] == 'waste_volume_balance_coverage']
    if not complete or 'waste_volume_balance_v1' not in capabilities or len(snapshots) != 1:
        result['issues'].append('Complete accumulated-waste evidence is unavailable; missing evidence is not zero volume.')
        return result
    snapshot = snapshots[0]
    result['event_ids'] = [snapshot['id']]
    try:
        data = json.loads(snapshot['row'].get('details', ''))
        if data.get('schema_version') != 1 or data.get('scope') != 'dynamic_accumulated_waste_only':
            raise ValueError('unsupported scope or schema')
        if any(type(data.get(key)) is not int or data[key] < 0 for key in ('group_count', 'allocation_count')):
            raise ValueError('invalid coverage counts')
        summaries = [event for event in events if event['type'] == 'waste_volume_balance_summary']
        allocations = [event for event in events if event['type'] == 'waste_volume_allocation']
        if data['group_count'] != len(summaries) or data['allocation_count'] != len(allocations):
            raise ValueError('incomplete group or allocation coverage')
        groups = [json.loads(event['row'].get('details', '')) for event in summaries]
        by_group = {}
        for allocation in allocations:
            entry = json.loads(allocation['row'].get('details', ''))
            by_group.setdefault(entry.pop('group'), []).append(entry)
        for group in groups:
            group['collections'] = by_group.pop(group['group'], [])
        if by_group:
            raise ValueError('allocation has no group summary')
        result['event_ids'].extend(event['id'] for event in summaries + allocations)
        seen_groups, seen_tasks = set(), set()
        totals = {key: 0.0 for key in FIELDS}
        evidence_by_task = {}
        for event in events:
            for task_id in event['task_ids']:
                evidence_by_task.setdefault(task_id, []).append(event)
        for group in groups:
            if not isinstance(group.get('group'), str) or group['group'] in seen_groups:
                raise ValueError('missing or duplicate group identity')
            seen_groups.add(group['group'])
            for key in (*FIELDS, 'difference_m3'):
                value = group[key]
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or (key != 'difference_m3' and value < 0)):
                    raise ValueError('invalid volume value')
            collections = group['collections']
            if not isinstance(collections, list):
                raise ValueError('collections must be a list')
            allocated = {key: 0.0 for key in STATUS_FIELDS.values()}
            for collection in collections:
                task_id, status, volume = collection['task_id'], collection['status'], collection['volume_m3']
                if (not isinstance(task_id, str) or not task_id or task_id in seen_tasks or status not in STATUS_FIELDS
                        or isinstance(volume, bool) or not isinstance(volume, (int, float))
                        or not math.isfinite(volume) or volume <= 0):
                    raise ValueError('invalid or duplicated allocation')
                seen_tasks.add(task_id)
                allocated[STATUS_FIELDS[status]] += volume
                records = evidence_by_task.get(task_id, [])
                generated = [event for event in records if event['type'] == 'task_generated']
                terminal = {event['type'] for event in records
                            if event['type'] in {'task_complete', 'multi_stop_task_complete', 'task_failed'}}
                if status in {'restored', 'unconfirmed'}:
                    valid_terminal = terminal == {'task_failed'}
                elif status == 'completed':
                    valid_terminal = bool(terminal) and 'task_failed' not in terminal
                else:
                    valid_terminal = not terminal
                if len(generated) != 1 or not valid_terminal:
                    result['issues'].append(f'{task_id}: allocation lacks consistent generation/outcome evidence.')
                elif not math.isclose(float(generated[0]['row'].get('waste_volume_m3', 0)), volume, rel_tol=1e-9, abs_tol=1e-6):
                    result['issues'].append(f'{task_id}: generated event volume differs from allocation.')
                result['event_ids'].extend(event['id'] for event in records
                    if event['type'] in {'task_generated', 'task_complete', 'multi_stop_task_complete', 'task_failed'})
            for field, value in allocated.items():
                if not math.isclose(value, group[field], rel_tol=1e-9, abs_tol=1e-10):
                    result['issues'].append(f"{group['group']}: {field} differs from task allocations.")
            difference = group['accrued_m3'] - sum(group[key] for key in
                ('residual_m3', 'pending_m3', 'completed_m3', 'unconfirmed_m3'))
            if not math.isclose(difference, 0, abs_tol=1e-9) or not math.isclose(difference, group['difference_m3'], abs_tol=1e-9):
                result['issues'].append(f"{group['group']}: accrued volume does not reconcile.")
            for key in FIELDS:
                totals[key] += group[key]
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        result['issues'].append('Malformed accumulated-waste summary; its totals cannot be established.')
        return result
    result.update(known=True, matches=not result['issues'], totals=totals, groups=groups,
                  event_ids=sorted(set(result['event_ids'])))
    return result
