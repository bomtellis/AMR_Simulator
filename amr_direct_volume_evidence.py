"""Task-attached event volumes, kept separate from accumulated stock pools."""
import json
import math

STATES = ('pending', 'completed', 'failed_before_pickup', 'unconfirmed')
FIELDS = ('requested_m3', *(state + '_m3' for state in STATES))


def _number(value, signed=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or (not signed and value < 0)):
        raise ValueError('invalid direct-event volume')
    return value


def summarize_direct_volume(events, *, complete, capabilities):
    result = {'known': False, 'matches': None, 'totals': {key: None for key in FIELDS},
              'event_ids': [], 'groups': [], 'issues': []}
    coverage = [e for e in events if e['type'] == 'direct_event_volume_coverage']
    if not complete or 'direct_event_volume_v1' not in capabilities or len(coverage) != 1:
        result['issues'].append('Direct-event volume outcomes require complete recorded task accounting; missing or older evidence is unknown, not zero volume.')
        return result
    result['event_ids'] = [coverage[0]['id']]
    try:
        manifest = json.loads(coverage[0]['row'].get('details', ''))
        if manifest.get('schema_version') != 1 or manifest.get('scope') != 'generated_direct_event_volume':
            raise ValueError('unknown direct-event scope')
        summaries = [e for e in events if e['type'] == 'direct_event_volume_summary']
        requests = [e for e in events if e['type'] == 'direct_event_volume_request']
        for key, rows in [('group_count', summaries), ('request_count', requests)]:
            if type(manifest.get(key)) is not int or manifest[key] != len(rows):
                raise ValueError('incomplete direct-event coverage')
        groups = {}
        for event in summaries:
            row = json.loads(event['row'].get('details', ''))
            key = (row['rule_id'], row['component'])
            if (not isinstance(key[0], str) or not key[0] or key[1] not in {'scheduled', 'sporadic'} or key in groups):
                raise ValueError('invalid or duplicate group')
            for field in FIELDS:
                _number(row[field])
            _number(row['difference_m3'], signed=True)
            groups[key] = row
        by_task = {}
        for event in events:
            for task in event['task_ids']:
                by_task.setdefault(task, []).append(event)
        allocations = {key: {field: 0.0 for field in FIELDS} for key in groups}
        seen = set()
        for event in requests:
            row = json.loads(event['row'].get('details', ''))
            task, state, volume = row['task_id'], row['status'], _number(row['volume_m3'])
            key = (row['rule_id'], row['component'])
            if (not isinstance(task, str) or not task or task in seen or task not in event['task_ids']
                    or state not in STATES or key not in groups):
                raise ValueError('invalid or duplicate direct-event request')
            seen.add(task)
            allocations[key]['requested_m3'] += volume
            allocations[key][state + '_m3'] += volume
            evidence = by_task.get(task, [])
            generated = [e for e in evidence if e['type'] == 'task_generated']
            terminal = {e['type'] for e in evidence if e['type'] in {'task_complete', 'multi_stop_task_complete', 'task_failed'}}
            valid_outcome = (not terminal if state == 'pending' else terminal == {'task_failed'}
                             if state in {'failed_before_pickup', 'unconfirmed'} else bool(terminal) and 'task_failed' not in terminal)
            if len(generated) != 1 or not valid_outcome:
                result['issues'].append(f'{task}: direct volume lacks consistent generation/outcome records.')
            elif (generated[0]['row'].get('source_rule_id') != key[0] or
                    generated[0]['row'].get('generation_component') != key[1] or
                    not math.isclose(float(generated[0]['row'].get('waste_volume_m3', 'nan')), volume, rel_tol=1e-9, abs_tol=1e-6)):
                result['issues'].append(f'{task}: generated rule or volume differs from direct-event accounting.')
            pickups = [e for e in evidence if e['type'] == 'location_payload_exit' and e['payload_instance_id']]
            if (state == 'unconfirmed' and not pickups) or (state == 'failed_before_pickup' and pickups):
                result['issues'].append(f'{task}: recorded failure phase disagrees with physical pickup evidence.')
            # A task cannot spend volume from a stock pool and also register it
            # as a new direct event. Hybrid's two components have distinct tasks.
            if any(e['type'] == 'waste_volume_allocation' for e in evidence):
                result['issues'].append(f'{task}: volume is allocated to both direct demand and accumulated waste.')
            result['event_ids'].extend(e['id'] for e in evidence if e['type'] in {
                'task_generated', 'task_complete', 'multi_stop_task_complete', 'task_failed',
                'location_payload_exit', 'waste_volume_allocation'})
        for event in events:
            if event['type'] != 'task_generated' or not event['row'].get('generation_component'):
                continue
            if event['row']['generation_component'] not in {'scheduled', 'sporadic'}:
                raise ValueError('unknown generated volume component')
            if len(event['task_ids']) != 1 or event['task_ids'][0] not in seen:
                result['issues'].append('A generated direct-volume task has no corresponding request record.')
                result['event_ids'].append(event['id'])
        totals = {field: 0.0 for field in FIELDS}
        for key, row in groups.items():
            for field in FIELDS:
                if not math.isclose(row[field], allocations[key][field], rel_tol=1e-9, abs_tol=1e-10):
                    result['issues'].append(f'{key[0]} / {key[1]}: {field} differs from request records.')
                totals[field] += row[field]
            difference = row['requested_m3'] - sum(row[state + '_m3'] for state in STATES)
            if not math.isclose(difference, 0, abs_tol=1e-9) or not math.isclose(difference, row['difference_m3'], abs_tol=1e-9):
                result['issues'].append(f'{key[0]} / {key[1]}: direct-event volume does not reconcile.')
        result['event_ids'].extend(e['id'] for e in summaries + requests)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        result['issues'].append('Malformed or incomplete direct-event evidence; outcome volume is unknown.')
        return result
    result.update(known=True, matches=not result['issues'], totals=totals, groups=list(groups.values()),
                  event_ids=sorted(set(result['event_ids'])))
    return result
