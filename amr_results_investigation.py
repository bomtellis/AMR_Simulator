"""Evidence-based task timelines and reconciled, precisely defined metrics."""
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from amr_run_evidence import config_hash, file_hash, verified_simulation_mode
from report.amr_energy_evidence import summarize_energy
from amr_lift_evidence import check_lift_movements
from amr_waste_evidence import summarize_waste_volume
from amr_tracked_stock_evidence import summarize_tracked_stock
from amr_direct_volume_evidence import summarize_direct_volume

COMPLETED = {'task_complete', 'multi_stop_task_complete'}
ASSIGNED = {'task_assigned', 'multi_stop_task_assigned'}
MAX_EVENTS = 250000


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def task_ids(row):
    ids = {t.strip() for t in str(row.get('task_id', '')).split(',') if t.strip()}
    try:
        values = json.loads(row.get('multi_stop_task_ids') or '[]')
        if isinstance(values, list):
            ids.update(str(t).strip() for t in values if str(t).strip())
    except (ValueError, TypeError):
        pass
    return sorted(ids)


def _seconds(value, start):
    numeric = number(value)
    if numeric is not None:
        return numeric
    if value and start:
        try:
            return (datetime.fromisoformat(str(value)) - start).total_seconds()
        except (ValueError, TypeError):
            pass
    return None


def resolve_log(path):
    path = Path(path)
    if not path.is_dir():
        return path
    # Prefer the full log in this run folder, including after a folder move.
    for name in ('simulation_steps.csv', 'verbose.csv', 'visualiser_steps.csv'):
        if (path / name).is_file():
            return path / name
    manifest = path / 'run_manifest.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding='utf-8-sig'))
        for key in ('steps_csv', 'visualiser_csv'):
            name = Path(data.get('outputs', {}).get(key, '')).name
            if name and (path / name).is_file():
                return path / name
    raise ValueError('No simulation event CSV was found in this run folder.')


def load_investigation(path):
    source = resolve_log(path)
    if source.stat().st_size > 300 * 1024 * 1024:
        raise ValueError('This investigation viewer supports logs up to 300 MiB. The file has not been truncated.')
    digest = file_hash(source)
    findings, metadata, frozen, simulation_mode = [], {}, None, None
    sidecar = Path(str(source) + '.run.json')
    if sidecar.is_file():
        data = json.loads(sidecar.read_text(encoding='utf-8'))
        if data.get('log_sha256') != digest:
            findings.append('Log checksum differs from its run evidence. Frozen inputs and final summary are not trusted.')
        elif data.get('config_sha256') != config_hash(data.get('frozen_inputs')):
            findings.append('Frozen input checksum does not match. Input evidence and final summary are not trusted.')
        elif data.get('schema_version') != 1:
            findings.append('Unsupported run-evidence version. Treating this as an unverified log.')
        else:
            try:
                simulation_mode = verified_simulation_mode(data, data['frozen_inputs'])
            except ValueError:
                if 'simulation_mode' in data:
                    raise
                findings.append('Legacy simulation mode cannot be resolved. Input evidence and final summary are not trusted.')
            else:
                metadata, frozen = data, data['frozen_inputs']
            if (data.get('software') or {}).get('scope_version') != 2:
                findings.append('Legacy or unknown software fingerprint scope: application source coverage is incomplete or unverified. Recorded results remain available.')
    else:
        findings.append('No bound run-evidence sidecar. Legacy log: completeness and software version are unknown.')
        # Legacy launcher snapshots may be used as context only when the manifest
        # binds their bytes. Never use config_source or an editor's current state.
        manifest_path, config_path = source.parent / 'run_manifest.json', source.parent / 'config.json'
        if manifest_path.is_file() and config_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
            if manifest.get('config_sha256') == file_hash(config_path):
                frozen = json.loads(config_path.read_text(encoding='utf-8-sig'))
                try:
                    simulation_mode = verified_simulation_mode(manifest, frozen)
                except ValueError:
                    if 'simulation_mode' in manifest:
                        raise
                    findings.append('Legacy simulation mode cannot be resolved from the saved snapshot.')
                findings.append('Legacy launcher input snapshot verified against its manifest; the log itself is not bound to that snapshot.')
    start = None
    if frozen:
        try:
            start = datetime.fromisoformat(frozen.get('simulation', {}).get('start_datetime', ''))
        except ValueError:
            pass

    events, seen = [], {}
    with source.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if not ({'event_type', 'segment_type'} & set(reader.fieldnames or [])):
            raise ValueError('Select an event/segment CSV, not an aggregate report table.')
        for line, raw in enumerate(reader, 2):
            if len(events) >= MAX_EVENTS:
                raise ValueError(f'Log exceeds {MAX_EVENTS:,} events; nothing has been silently truncated.')
            if None in raw:
                raise ValueError(f'Malformed CSV row {line}: more values than columns.')
            row = {k: v or '' for k, v in raw.items()}
            native = row.get('event_id', '')
            eid = native or f'legacy:{digest[:20]}:{line}'
            if eid in seen:
                if row != seen[eid]:
                    raise ValueError(f'Conflicting records share event identifier {eid}.')
                findings.append(f'Duplicate event {eid} was counted once.')
                continue
            seen[eid] = row
            if metadata and row.get('run_id') != metadata.get('run_id'):
                raise ValueError(f'Row {line} belongs to a different or unspecified run.')
            kind = row.get('event_type') or ('segment_' + row['segment_type'] if row.get('segment_type') else 'unknown')
            if kind.startswith('multi_stop_segment_'):
                kind = kind.removeprefix('multi_stop_')
            elapsed = number(row.get('sim_time_sec'))
            if elapsed is None:
                elapsed = _seconds(row.get('start_time'), start)
            details = row.get('details', '')
            try:
                parsed = json.loads(details)
                if not isinstance(parsed, dict):
                    parsed = {}
            except (ValueError, TypeError):
                parsed = {}
            explanation = row.get('pending_reason') or row.get('scenario_reason') or details or 'No explanation was recorded.'
            if parsed and not row.get('pending_reason'):
                explanation = parsed.get('reason') or parsed.get('scenario_reason') or parsed.get('type') or kind
                if row.get('door_restricted', '').lower() in {'true', '1'}:
                    explanation += f"; door restriction: {row.get('door_nodes') or 'opening'}, effective width {row.get('corridor_width_m') or 'unknown'} m"
            events.append({'id': eid, 'identity': 'native' if native else 'legacy row identifier',
                           'source_line': line, 'time_seconds': elapsed, 'type': kind,
                           'task_ids': task_ids(row), 'amr_id': row.get('amr_id', ''),
                           'journey_id': row.get('journey_id', ''), 'payload_instance_id': row.get('payload_instance_id', ''),
                           'lift_id': row.get('lift_id', ''), 'explanation': str(explanation),
                           'evidence_kind': 'planned segment' if kind.startswith('segment_') else 'recorded event',
                           'duration_seconds': number(row.get('duration_sec')),
                           'wait_seconds': number(row.get('wait_time_sec')),
                           'row': row})
    if file_hash(source) != digest:
        raise ValueError('The log changed while it was being read. Wait for the run to finish and reopen it.')
    events.sort(key=lambda e: (e['time_seconds'] is None, e['time_seconds'] or 0, e['source_line']))
    complete_evidence = bool(metadata and metadata.get('run_status') == 'finished'
                             and metadata.get('logging_enabled') and not metadata.get('reduced_logging')
                             and metadata.get('log_kind') == 'full')
    if not complete_evidence:
        findings.append('This log does not establish full-run coverage. No observed activity is not proof of zero activity.')
    if metadata.get('log_kind') == 'playback':
        findings.append('Playback CSV is filtered. Use the full simulation_steps.csv for investigation.')
    return investigate_events(events, frozen, metadata, findings, source=str(source), log_hash=digest,
                              complete_evidence=complete_evidence, simulation_mode=simulation_mode)


def investigate_events(events, frozen=None, metadata=None, findings=None, *, source='', log_hash='',
                       complete_evidence=False, simulation_mode=None):
    metadata, findings = metadata or {}, list(findings or [])
    if simulation_mode is None and frozen is not None:
        try:
            simulation_mode = verified_simulation_mode(metadata, frozen)
        except ValueError:
            if 'simulation_mode' in metadata:
                raise
    by_task = defaultdict(list)
    for event in events:
        for task in event['task_ids']:
            by_task[task].append(event)
    configured = {str(t.get('id')): t for t in (frozen or {}).get('tasks', [])}
    tasks = []
    for task_id in sorted(set(by_task) | set(configured)):
        records = by_task[task_id]
        terminal = [e for e in records if e['type'] in COMPLETED | {'task_failed'}]
        outcomes = {'completed' if e['type'] in COMPLETED else 'failed' for e in terminal}
        outcome = 'conflicting outcomes' if len(outcomes) > 1 else next(iter(outcomes)) if outcomes else 'outcome not recorded'
        if len(outcomes) > 1:
            findings.append(f'{task_id}: both completion and failure are recorded.')
        release = next((e for e in records if e['type'] == 'task_released' and e['time_seconds'] is not None), None)
        assignment = next((e for e in records if e['type'] in ASSIGNED and e['time_seconds'] is not None), None)
        finish = next((e for e in reversed(records) if e['type'] in COMPLETED and e['time_seconds'] is not None), None)
        delay = assignment['time_seconds'] - release['time_seconds'] if release and assignment else None
        elapsed = finish['time_seconds'] - release['time_seconds'] if release and finish else None
        if delay is not None and delay < 0 or elapsed is not None and elapsed < 0:
            findings.append(f'{task_id}: event chronology is inconsistent.')
        reasons = [e for e in records if e['row'].get('pending_reason') or 'wait' in e['type'] or 'pending' in e['type'] or e['type'] == 'task_failed' or 'defer' in e['type']]
        origin = next((e for e in records if e['row'].get('source_rule_path')), None)
        profile = next((e['row']['route_profile'] for e in records if e['row'].get('route_profile')), '')
        tasks.append({'task_id': task_id, 'outcome': outcome,
                      'release_seconds': release['time_seconds'] if release else None,
                      'assignment_seconds': assignment['time_seconds'] if assignment else None,
                      'completion_seconds': finish['time_seconds'] if finish else None,
                      'assignment_delay_seconds': delay if delay is None or delay >= 0 else None,
                      'release_to_completion_seconds': elapsed if elapsed is None or elapsed >= 0 else None,
                      'delay_explanation': ('Recorded wait/deferral reasons available below.' if reasons else
                                            'No delay reason recorded.' if delay else 'No assignment delay measured.' if delay == 0 else 'Release or assignment evidence is missing.'),
                      'reason_event_ids': [e['id'] for e in reasons], 'event_ids': [e['id'] for e in records],
                      'assignment_delay_evidence': [e['id'] for e in (release, assignment) if e],
                      'duration_evidence': [e['id'] for e in (release, finish) if e],
                      'source_rule_path': origin['row'].get('source_rule_path', '') if origin else '',
                      'route_profile': profile,
                      'profile_definition': (frozen or {}).get('route_profiles', {}).get(profile),
                      'configured_request': configured.get(task_id),
                      'missing_evidence': [name for name, value in [('release', release), ('assignment', assignment), ('terminal outcome', terminal)] if not value]})

    # A service arrival ends a physical transfer without occupying inventory.
    # It must be recorded explicitly; never infer it from a planned segment.
    departures, payload_moves = {}, []
    payload_anomalies = []
    payload_gaps = False
    for e in events:
        if e['type'] not in {'location_payload_exit', 'location_payload_enter', 'payload_service_arrival'}:
            continue
        pid = e['payload_instance_id']
        if not pid or e['time_seconds'] is None:
            payload_gaps = True
            payload_anomalies.append({'reason': 'Payload identity or event time is missing.', 'event_ids': [e['id']]})
            continue
        row = e['row']
        if e['type'] == 'location_payload_exit':
            if pid in departures:
                payload_gaps = True
                payload_anomalies.append({'reason': f'{pid}: another exit was recorded before a subsequent arrival.',
                                          'event_ids': [departures[pid]['id'], e['id']]})
            departures[pid] = e
        elif pid in departures:
            previous = departures.pop(pid)
            origin = previous['row'].get('from_location') or previous['row'].get('to_location')
            destination = row.get('to_location') or row.get('from_location')
            if origin and destination and origin != destination:
                payload_moves.append({'payload_instance_id': pid, 'origin': origin, 'destination': destination,
                                      'start_seconds': previous['time_seconds'], 'end_seconds': e['time_seconds'],
                                      'event_ids': [previous['id'], e['id']]})
    payload_gaps = payload_gaps or bool(departures)

    journeys = {}
    for e in events:
        if e['type'] not in ASSIGNED:
            continue
        jid = e['journey_id']
        quality = 'native journey identifier'
        if not jid:
            batch = re.search(r'(?:^|;)\s*batch=([^;]+)', e['row'].get('details', ''))
            members = sorted(t.strip() for t in batch.group(1).split(',')) if batch else e['task_ids']
            if e['type'] == 'multi_stop_task_assigned' and not batch:
                findings.append('A legacy multi-stop assignment lacks a batch identifier; journey totals are incomplete.')
                continue
            jid = 'reconstructed:' + config_hash([e['amr_id'], e['time_seconds'], members])[:20]
            quality = 'reconstructed from assignment time, AMR and batch'
        journey = journeys.setdefault(jid, {'journey_id': jid, 'quality': quality, 'amr_id': e['amr_id'], 'task_ids': [], 'event_ids': []})
        journey['task_ids'] = sorted(set(journey['task_ids']) | set(e['task_ids']))
        journey['event_ids'].append(e['id'])
    lifts = [e for e in events if e['type'] in {'segment_lift_transfer', 'segment_lift_reposition'}]
    metrics = []

    def metric(key, title, value, evidence, definition, *, known=complete_evidence):
        metrics.append({'key': key, 'title': title, 'value': value if value or known else None,
                        'observed_count': value, 'coverage': 'full bound log' if known else 'partial or unknown coverage',
                        'definition': definition, 'event_ids': sorted(set(evidence))})

    metric('tasks', 'Tasks observed', len(by_task), [e['id'] for e in events if e['task_ids']],
           'Distinct task identifiers present in recorded events; shared segment task lists are split, not counted as an extra task.')
    for kind, title in [('completed', 'Completed tasks'), ('failed', 'Failed tasks')]:
        chosen = [t for t in tasks if t['outcome'] == kind]
        chosen_ids = {t['task_id'] for t in chosen}
        metric(kind, title, len(chosen), [e['id'] for e in events if chosen_ids.intersection(e['task_ids']) and e['type'] in (COMPLETED if kind == 'completed' else {'task_failed'})],
               'Distinct tasks with this terminal outcome. Conflicting outcomes are excluded and flagged.')
    metric('unknown_outcome', 'Tasks without a recorded outcome', sum(t['outcome'] == 'outcome not recorded' for t in tasks),
           [eid for t in tasks if t['outcome'] == 'outcome not recorded' for eid in t['event_ids']],
           'Observed or explicitly configured tasks lacking completion/failure evidence; not automatically classified as pending.')
    for kind, title in [('charge_wait', 'Charging wait observations'), ('charge_cycle_failed', 'Failed charging attempts')]:
        records = [e for e in events if e['type'] == kind]
        metric(kind, title, len(records), [e['id'] for e in records],
               'Recorded robot charging events, separate from delivery task outcomes. Repeated unchanged wait reasons are suppressed; this count is not waiting duration. Missing or older event coverage is unknown.',
               known=complete_evidence and 'charge_cycle_arrivals_v1' in metadata.get('event_capabilities', []))
    metric('payload_moves', 'Payload transfers between locations', len(payload_moves), [eid for m in payload_moves for eid in m['event_ids']],
           'Paired exit and subsequent stored entry or service arrival for the same physical payload instance at different locations. Service handling does not imply inventory occupancy. Initial population is excluded.',
           known=complete_evidence and not payload_gaps)
    service_arrivals = [e for e in events if e['type'] == 'payload_service_arrival']
    lifecycle = {e['payload_instance_id']: e for e in events
                 if e['type'] == 'payload_instance_summary' and e['payload_instance_id']}
    lifecycle_known = complete_evidence and 'payload_lifecycle_summary' in metadata.get('event_capabilities', [])
    for state, title in [('planned', 'Planned container IDs, not issued'), ('stored', 'Containers stored at run end'),
                         ('in_transit', 'Containers in transit at run end'), ('staged', 'Containers staged for return'),
                         ('unconfirmed', 'Containers with unconfirmed arrival'), ('removed', 'Containers removed from the model')]:
        records = [e for e in lifecycle.values() if e['row'].get('status') == state]
        metric(f'payload_final_{state}', title, len(records), [e['id'] for e in records],
               f'Distinct container identities whose recorded final lifecycle state is {state}. Missing lifecycle evidence is unknown, not zero.',
               known=lifecycle_known)
    issued = [e for e in lifecycle.values() if e['row'].get('status') in
              {'stored', 'in_transit', 'staged', 'unconfirmed', 'removed'}]
    metric('payload_issued', 'Physical containers issued during the run', len(issued), [e['id'] for e in issued],
           'Distinct physically issued identities including initial stock and removed containers; excludes planned-only IDs. Not a simultaneous peak.',
           known=lifecycle_known)
    recovery, recovered = {}, []
    for event in events:
        identity = event['payload_instance_id']
        if event['type'] == 'payload_recovery_required' and identity:
            recovery[identity] = event
        elif event['type'] in {'payload_recovery_started', 'payload_recovery_completed'}:
            recovery.pop(identity, None)
            if event['type'] == 'payload_recovery_completed':
                recovered.append(event)
    recovery_known = complete_evidence and 'staged_payload_recovery' in metadata.get('event_capabilities', [])
    metric('payload_recovery_outstanding', 'Staged containers awaiting recovery', len(recovery),
           [e['id'] for e in recovery.values()],
           'Recovery-required identities without a later recorded recovery pickup. Recovery in transit is counted separately by lifecycle state.', known=recovery_known)
    metric('payload_recovery_completed', 'Confirmed recovery arrivals', len(recovered), [e['id'] for e in recovered],
           'Explicit recovery tasks with a confirmed destination arrival and storage event; earlier failed task outcomes remain unchanged.', known=recovery_known)
    if recovery:
        findings.append('A failed task left a staged container awaiting recovery. No recovery movement or storage bay has been assumed.')

    metric('payload_service_arrivals', 'Payload service arrivals outside storage', len(service_arrivals),
           [e['id'] for e in service_arrivals],
           'Recorded arrivals for same-container servicing without occupying a storage bay. These are physical journey endpoints, not extra payload instances or stored stock.',
           known=complete_evidence and 'payload_service_arrivals' in metadata.get('event_capabilities', []))
    metric('payload_unpaired_exits', 'Payload exits without a later arrival', len(departures), [e['id'] for e in departures.values()],
           'Recorded payload exits with no subsequent stored entry or service arrival for the same instance in this log. Select to inspect evidence gaps; these are not automatically payload losses.')
    metric('payload_tracking_conflicts', 'Payload tracking conflicts', len(payload_anomalies), [eid for a in payload_anomalies for eid in a['event_ids']],
           'Repeated exits before the next entry, or physical movement records missing an instance identifier/time. Select the contributing records to investigate; the reader does not repair them.')
    metric('journeys', 'Assigned AMR journeys', len(journeys), [eid for j in journeys.values() for eid in j['event_ids']],
           'Distinct assigned route plans. A multi-stop batch is one journey even when several task assignments are logged. This is not a completed-journey metric.',
           known=complete_evidence and all(e['journey_id'] for e in events if e['type'] in ASSIGNED))
    metric('lift_segments', 'Planned lift movements', len(lifts), [e['id'] for e in lifts],
           'Transfer and empty reposition segment records, each counted once regardless of carried task count. These are logged route-plan movements, not independent execution confirmations.')
    lift_checks = check_lift_movements(events, frozen, complete=complete_evidence,
        capabilities=metadata.get('event_capabilities', []),
        expected=metadata.get('summary', {}).get('lift_movement_counts'))
    for kind, title, definition in (
        ('floor_discontinuity', 'Unexplained recorded lift floor changes',
         'Movement origins differing from the preceding destination or frozen initial floor. Malformed sequences are not bridged. Observations in partial logs may reflect missing movements.'),
        ('overlap', 'Overlapping planned lift movements',
         'Movement starts while an earlier movement of the same lift is still active, with 2 ms tolerance for CSV rounding. Each conflicting start counts once and links to a prior overlapping movement; this is not a count of all interval pairs.'),
        ('count_mismatch', 'Lift booking/log count mismatches',
         'Lifts whose recorded transfer/reposition counts differ from counts independently derived from final bookings. Missing final counts remain unknown.')):
        problems = [p for p in lift_checks['issues'] if p['kind'] == kind]
        metric('lift_' + kind, title, len(problems), [eid for p in problems for eid in p['event_ids']],
               definition, known=lift_checks['known'])
    for record in lift_checks['records']:
        if record['status'] == 'Conflict':
            findings.append(f"Lift movement evidence conflict for {record['lift_id']}: inspect the Lift checks workspace.")
    if not lift_checks['known']:
        findings.append('Complete lift movement consistency is not established; inspect bound inputs, movement records and final booking counts.')
    energy = summarize_energy((e['row'] for e in events), complete=complete_evidence,
                              capabilities=metadata.get('event_capabilities', []),
                              expected_amrs=metadata.get('summary', {}).get('battery_amr_ids'))
    for energy_source, record in energy['sources'].items():
        metrics.append({'key': energy_source + '_energy_kwh', 'title': record['title'] + ' (kWh)',
            'value': record['value_kwh'], 'observed_count': record['observed_kwh'],
            'coverage': 'full bound attribution' if record['known'] else 'partial or unknown attribution',
            'definition': 'Sum of explicitly source-attributed movement energy, once per event ID. Shared tasks do not multiply a journey. Planned energy, not measured execution; charging input is excluded.',
            'event_ids': record['event_ids'] + record['missing_event_ids']})
    for journey_id, record in energy['journeys'].items():
        if journey_id in journeys:
            journeys[journey_id]['observed_energy_kwh'] = record['amr_battery'] + record['lift_supply']
            journeys[journey_id]['energy_event_ids'] = record['event_ids']
    if not all(record['known'] for record in energy['sources'].values()):
        findings.append('Complete source-attributed energy is not established. Legacy, filtered or incomplete movement evidence is not zero consumption.')
    battery = energy['battery']
    metrics.append({'key': 'battery_charge_applied_kwh', 'title': 'Applied battery charging (kWh)',
        'value': battery['applied_charge_kwh'], 'observed_count': battery['observed_applied_charge_kwh'],
        'coverage': 'full bound model accounting' if battery['known'] else 'partial or unknown accounting',
        'definition': 'Charge energy explicitly credited to the model battery. Separate charge cycles credit at completion; in-place route charges credit during commitment. Not measured wall-supply consumption or continuous physical state.',
        'event_ids': battery['charge_event_ids']})
    for record in battery['records']:
        metrics.append({'key': 'battery_balance_' + record['amr_id'],
            'title': 'Model battery balance: ' + record['amr_id'],
            'value': record['status'] if record['known'] else None,
            'observed_count': record['residual_kwh'], 'coverage': record['status'],
            'definition': (f"Initial {record['initial_kwh']} kWh + applied charge {record['applied_charge_kwh']} kWh "
                f"- planned traction {record['planned_traction_kwh']} kWh - final {record['final_kwh']} kWh. "
                'Residual must be zero within 1e-9 kWh; charge and traction records must also match the recorded counters. This is model accounting, not continuous physical state.'),
            'event_ids': record['event_ids']})
        if record['matches'] is False:
            findings.append(f"Battery accounting mismatch for {record['amr_id']}: inspect charge, movement and summary evidence.")
    if not battery['known']:
        findings.append('Complete battery balance is not established; applied charging and final model state require bound accounting evidence.')
    waste = summarize_waste_volume(events, complete=complete_evidence,
                                  capabilities=metadata.get('event_capabilities', []))
    waste_scope = ('Dynamic and legacy accumulated waste. ' if waste['scope'] == 'dynamic_and_legacy_accumulated_waste'
                   else 'Dynamic accumulated waste only; legacy generators are outside this older evidence. '
                   if waste['scope'] == 'dynamic_accumulated_waste_only' else 'Accumulated-waste scope is not established. ')
    for field, title in [('accrued_m3', 'accrued'), ('residual_m3', 'remaining unallocated'),
                         ('pending_m3', 'allocated to pending collections'), ('completed_m3', 'completed collections'),
                         ('unconfirmed_m3', 'unconfirmed after pickup'), ('restored_after_failure_m3', 'restored after failed attempts')]:
        metrics.append({'key': 'waste_' + field, 'title': f'Accumulated waste: {title} (m³)',
            'value': waste['totals'][field], 'observed_count': waste['totals'][field],
            'coverage': 'recorded model balance' if waste['known'] else 'missing or incomplete evidence',
            'definition': waste_scope + 'Accrued = remaining unallocated + pending + completed + unconfirmed. Restored volume is already included in residual or later allocations and must not be added again. Ordinary scheduled/sporadic waste is outside this balance.',
            'event_ids': waste['event_ids']})
    metrics.append({'key': 'waste_volume_balance', 'title': 'Accumulated waste reconciliation',
        'value': ('Reconciled' if waste['matches'] else 'Conflict') if waste['known'] else None,
        'observed_count': None, 'coverage': 'recorded model balance' if waste['known'] else 'missing or incomplete evidence',
        'definition': 'Checks recorded group totals, task allocations, generated volumes and terminal outcomes. A completed collection is not evidence of physical disposal or decontamination.',
        'event_ids': waste['event_ids']})
    findings.extend(waste['issues'])
    direct = summarize_direct_volume(events, complete=complete_evidence,
                                     capabilities=metadata.get('event_capabilities', []))
    direct_definition = ('Volume explicitly attached to generated scheduled waste and sporadic tasks, including hybrid direct events. '
        'Requested = pending + completed + failed before pickup + unconfirmed after pickup. '
        'Task completion is not proof of staff handoff, physical disposal or decontamination. '
        'This volume is separate from accumulated waste pools; failed direct events are not automatically retried.')
    for field, title in [('requested_m3', 'requested'), ('pending_m3', 'pending'),
                         ('completed_m3', 'completed tasks'), ('failed_before_pickup_m3', 'failed before pickup'),
                         ('unconfirmed_m3', 'unconfirmed after pickup')]:
        metrics.append({'key': 'direct_event_' + field, 'title': f'Direct-event volume: {title} (m³)',
            'value': direct['totals'][field], 'observed_count': direct['totals'][field],
            'coverage': 'recorded task-volume accounting' if direct['known'] else 'missing or incomplete evidence',
            'definition': direct_definition, 'event_ids': direct['event_ids']})
    metrics.append({'key': 'direct_event_volume_balance', 'title': 'Direct-event volume reconciliation',
        'value': ('Reconciled' if direct['matches'] else 'Conflict') if direct['known'] else None,
        'observed_count': None, 'coverage': 'recorded task-volume accounting' if direct['known'] else 'missing or incomplete evidence',
        'definition': direct_definition, 'event_ids': direct['event_ids']})
    findings.extend(direct['issues'])
    stock = summarize_tracked_stock(events, complete=complete_evidence,
                                   capabilities=metadata.get('event_capabilities', []))
    metrics.append({'key': 'tracked_stock_reconciliation', 'title': 'Tracked stock reconciliation',
        'value': ('Reconciled' if stock['matches'] else 'Conflict') if stock['known'] else None,
        'observed_count': None, 'coverage': 'recorded item balances and delivery receipts' if stock['known'] else 'missing or incomplete evidence',
        'definition': 'Checks each item/resource balance, generated request quantities, confirmed delivery/handoff receipts and physical arrivals. Different item units are never added together. Older snapshots without delivery receipts remain unknown.',
        'event_ids': stock['event_ids']})
    for index, record in enumerate(stock['records']):
        identity = f"{record['rule_id']} / {record['location'] or 'pooled'} / {record['item']}"
        definition = (f"Initial {record['initial']:g} + supplied {record['delivered']:g} = consumed {record['consumed']:g} "
            f"+ removed {record['removed']:g} + remaining {record['remaining']:g}. Unmet consumption {record['unmet']:g} is separate. "
            'Logical item units; initially full stock and configured-source supply assumptions apply. This validates recorded accounting, not an independent recalculation of every consumption interval.')
        for field, label in [('remaining', 'Remaining stock'), ('unmet', 'Unmet consumption'), ('matches', 'Stock balance')]:
            metrics.append({'key': f'tracked_stock_{index}_{field}', 'title': f'{label}: {identity}',
                'value': ('Reconciled' if record['matches'] else 'Conflict') if field == 'matches' else record[field],
                'observed_count': None if field == 'matches' else record[field], 'coverage': 'recorded item accounting',
                'definition': definition, 'event_ids': record['event_ids']})
    findings.extend(stock['issues'])
    if payload_gaps:
        findings.append('Payload movement evidence has missing identifiers/times, repeated exits or unpaired exits; transfer totals may be incomplete.')
        findings.extend(a['reason'] for a in payload_anomalies)
    reconciliation = []
    if metadata.get('summary') and complete_evidence:
        for outcome, key in [('completed', 'completed_task_ids'), ('failed', 'failed_task_ids')]:
            expected = set(metadata['summary'].get(key, []))
            observed = {t['task_id'] for t in tasks if t['outcome'] == outcome}
            reconciliation.append({'outcome': outcome, 'recorded_summary_count': len(expected), 'event_count': len(observed),
                                   'matches': expected == observed, 'missing_from_events': sorted(expected - observed),
                                   'missing_from_summary': sorted(observed - expected)})
    return {'schema_version': 1, 'source': source, 'log_sha256': log_hash, 'run_id': metadata.get('run_id'),
            'complete_evidence': complete_evidence, 'frozen_inputs': frozen,
            'simulation_mode': simulation_mode,
            'software': metadata.get('software'), 'project_binding': metadata.get('project_binding'), 'findings': sorted(set(findings)),
            'tasks': tasks, 'events': events, 'metrics': metrics, 'payload_movements': payload_moves,
            'payload_tracking_findings': payload_anomalies,
            'journeys': list(journeys.values()), 'reconciliation': reconciliation, 'energy': energy,
            'lift_checks': lift_checks, 'tracked_stock': stock, 'direct_event_volume': direct,
            'limitations': ['Wait intervals can overlap and are not summed into an additive delay breakdown.',
                            'Route-plan segments may be logged ahead of execution; completion is established only by terminal events.',
                            'Missing events, reasons or physical identifiers are not reconstructed from the current project.',
                            'Legacy identities are stable for unchanged file bytes; editing or reordering a legacy log changes them.']}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = load_investigation(args.source)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"{len(result['tasks'])} tasks, {len(result['events'])} evidence records")
