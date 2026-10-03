"""Reconcile recorded consumable balances without combining unlike item units."""
import json
import math

FIELDS = ('initial', 'delivered', 'consumed', 'removed', 'remaining', 'unmet')
TERMINAL = {'task_complete', 'multi_stop_task_complete', 'task_failed'}
MODES = {'top_up_only', 'full_exchange', 'replace_empty'}


def _number(value, *, signed=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or (not signed and value < 0)):
        raise ValueError('invalid stock quantity')
    return value


def _quantities(value):
    if not isinstance(value, dict) or not value:
        raise ValueError('missing item quantities')
    for name, amount in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError('invalid item name')
        _number(amount)
    return value


def _same(left, right):
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-10)


def summarize_tracked_stock(events, *, complete, capabilities):
    result = {'known': False, 'matches': None, 'records': [], 'event_ids': [], 'issues': []}
    coverage = [e for e in events if e['type'] == 'tracked_stock_coverage']
    required = {'tracked_stock_balance_v1', 'tracked_stock_delivery_v1'}
    if not complete or not required.issubset(capabilities) or len(coverage) != 1:
        result['issues'].append('Complete tracked-stock reconciliation is unavailable; older snapshots without delivery receipts and partial logs are unknown, not zero stock.')
        return result
    result['event_ids'] = [coverage[0]['id']]
    try:
        manifest = json.loads(coverage[0]['row'].get('details', ''))
        if manifest.get('schema_version') != 1 or manifest.get('scope') != 'dynamic_tracked_stock':
            raise ValueError('unsupported stock evidence schema')
        selected = {}
        for count, kind in [('balance_count', 'tracked_stock_balance_summary'),
                            ('request_count', 'tracked_stock_request'),
                            ('delivery_count', 'tracked_stock_delivery_confirmed')]:
            selected[kind] = [e for e in events if e['type'] == kind]
            if type(manifest.get(count)) is not int or manifest[count] != len(selected[kind]):
                raise ValueError('incomplete stock coverage')
            result['event_ids'].extend(e['id'] for e in selected[kind])
        records = {}
        for event in selected['tracked_stock_balance_summary']:
            row = json.loads(event['row'].get('details', ''))
            key = (row['rule_id'], row['location'], row['item'])
            if (any(not isinstance(value, str) for value in key) or not key[0] or not key[2] or key in records):
                raise ValueError('invalid or duplicate stock identity')
            for field in FIELDS:
                _number(row[field])
            _number(row['difference'], signed=True)
            row.update(event_ids=[coverage[0]['id'], event['id']], issues=[], confirmed_delivered=0.0, confirmed_removed=0.0)
            records[key] = row
            difference = row['initial'] + row['delivered'] - row['consumed'] - row['removed'] - row['remaining']
            if not _same(row['initial'] + row['delivered'], row['consumed'] + row['removed'] + row['remaining']) or not _same(difference, row['difference']):
                row['issues'].append('Initial + delivered does not equal consumed + removed + remaining.')
        by_task = {}
        for event in events:
            for task_id in event['task_ids']:
                by_task.setdefault(task_id, []).append(event)
        seen_requests = set()
        for event in selected['tracked_stock_request']:
            request = json.loads(event['row'].get('details', ''))
            task_id = request['task_id']
            if not isinstance(task_id, str) or not task_id or task_id in seen_requests:
                raise ValueError('invalid or duplicate stock request')
            if task_id not in event['task_ids'] or request['mode'] not in MODES or request['status'] not in {'pending', 'delivered', 'failed'}:
                raise ValueError('invalid request state or identity')
            seen_requests.add(task_id)
            quantities = _quantities(request['quantities'])
            affected = [records[(request['rule_id'], request['resource'], item)] for item in quantities]
            task_events = by_task.get(task_id, [])
            generated = [e for e in task_events if e['type'] == 'task_generated']
            receipts = [e for e in task_events if e['type'] == 'tracked_stock_delivery_confirmed']
            terminal = {e['type'] for e in task_events if e['type'] in TERMINAL}
            issues = []
            if len(generated) != 1:
                issues.append('Request lacks one corresponding generated-task record.')
            else:
                metadata = json.loads(generated[0]['row'].get('tracked_items') or '{}')
                if set(metadata) != set(quantities) or any(not _same(_number(metadata[item]['delivery_quantity']), amount)
                                                          for item, amount in quantities.items()):
                    issues.append('Requested quantities differ from generated-task item quantities.')
            zone = bool(generated and generated[0]['row'].get('dropoff_zone'))
            if request['status'] == 'delivered':
                if len(receipts) != 1 or not terminal or 'task_failed' in terminal:
                    issues.append('Delivered request lacks one receipt and a consistent completed task.')
            elif receipts or (request['status'] == 'failed' and terminal != {'task_failed'}) or (
                    request['status'] == 'pending' and (terminal and (not zone or 'task_failed' in terminal))):
                issues.append('Pending/failed request contradicts its delivery or task outcome records.')
            for receipt_event in receipts:
                receipt = json.loads(receipt_event['row'].get('details', ''))
                supplied, removed = _quantities(receipt['quantities']), _quantities(receipt['removed'])
                if (receipt['rule_id'] != request['rule_id'] or receipt['resource'] != request['resource']
                        or receipt['mode'] != request['mode'] or set(supplied) != set(quantities)
                        or set(removed) != set(quantities)):
                    raise ValueError('receipt identity or items disagree with request')
                if any(not _same(supplied[item], amount) for item, amount in quantities.items()):
                    issues.append('Receipt supply differs from requested quantity.')
                if request['mode'] != 'full_exchange' and any(removed.values()):
                    issues.append('A non-exchange delivery claims removed contents.')
                expected_confirmation = 'tracked_items_delivered' if zone else 'completed'
                if receipt['confirmation'] != expected_confirmation:
                    issues.append('Receipt uses the wrong direct-delivery/staff-handoff confirmation.')
                receipt_time = receipt_event['time_seconds']
                terminal_times = [e['time_seconds'] for e in task_events if e['type'] in TERMINAL and e['type'] != 'task_failed']
                if (receipt_time is None or not terminal_times or any(t is None for t in terminal_times)
                        or receipt_time + 0.001 < max(terminal_times)
                        or (not zone and abs(receipt_time - max(terminal_times)) > 0.001)):
                    issues.append('Receipt time is inconsistent with confirmed task completion.')
                destination = request['resource'] or (generated[0]['row'].get('to_location') if generated else '')
                physical = [e for e in task_events if e['type'] in {'location_payload_enter', 'payload_service_arrival'}
                            and e['row'].get('to_location') == destination
                            and receipt_time is not None and e['time_seconds'] is not None
                            and e['time_seconds'] <= receipt_time + 0.001
                            and e['payload_instance_id'] and e['payload_instance_id'] == receipt_event['payload_instance_id']]
                if not physical:
                    issues.append('Receipt lacks corresponding physical arrival at the stock resource.')
                for item in quantities:
                    row = records[(request['rule_id'], request['resource'], item)]
                    row['confirmed_delivered'] += supplied[item]
                    row['confirmed_removed'] += removed[item]
            links = [event['id']] + [e['id'] for e in task_events if e['type'] in TERMINAL | {
                'task_generated', 'tracked_stock_delivery_confirmed', 'location_payload_enter', 'payload_service_arrival'}]
            for row in affected:
                row['event_ids'].extend(links)
                row['issues'].extend(f'{task_id}: {issue}' for issue in issues)
        if any(not e['task_ids'] or any(task not in seen_requests for task in e['task_ids'])
               for e in selected['tracked_stock_delivery_confirmed']):
            result['issues'].append('A stock delivery receipt has no corresponding request.')
        for row in records.values():
            if not _same(row['delivered'], row['confirmed_delivered']) or not _same(row['removed'], row['confirmed_removed']):
                row['issues'].append('Final supplied/removed counters differ from confirmed delivery receipts.')
            row['matches'] = not row['issues']
            row['event_ids'] = sorted(set(row['event_ids']))
            result['event_ids'].extend(row['event_ids'])
            result['issues'].extend(f"{row['rule_id']} / {row['location'] or 'pooled'} / {row['item']}: {issue}" for issue in row['issues'])
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        result['issues'].append('Malformed or incomplete tracked-stock evidence; its reconciliation is unknown.')
        return result
    result.update(known=True, matches=not result['issues'], records=list(records.values()),
                  event_ids=sorted(set(result['event_ids'])))
    return result
