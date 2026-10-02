"""Evidence-based task timelines and reconciled, precisely defined metrics."""
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from amr_run_evidence import config_hash, file_hash

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
    if source.stat().st_size > 150 * 1024 * 1024:
        raise ValueError('This investigation viewer supports logs up to 150 MiB. The file has not been truncated.')
    digest = file_hash(source)
    findings, metadata, frozen = [], {}, None
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
            metadata, frozen = data, data['frozen_inputs']
    else:
        findings.append('No bound run-evidence sidecar. Legacy log: completeness and software version are unknown.')
        # Legacy launcher snapshots may be used as context only when the manifest
        # binds their bytes. Never use config_source or an editor's current state.
        manifest_path, config_path = source.parent / 'run_manifest.json', source.parent / 'config.json'
        if manifest_path.is_file() and config_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
            if manifest.get('config_sha256') == file_hash(config_path):
                frozen = json.loads(config_path.read_text(encoding='utf-8-sig'))
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
                              complete_evidence=complete_evidence)


def investigate_events(events, frozen=None, metadata=None, findings=None, *, source='', log_hash='', complete_evidence=False):
    metadata, findings = metadata or {}, list(findings or [])
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

    # Payload transport is a paired physical exit and later entry for the same
    # instance, not a task count or the number of segment rows.
    departures, payload_moves = {}, []
    payload_anomalies = []
    payload_gaps = False
    for e in events:
        if e['type'] not in {'location_payload_exit', 'location_payload_enter'}:
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
                payload_anomalies.append({'reason': f'{pid}: another exit was recorded before a subsequent entry.',
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
    metric('payload_moves', 'Payload transfers between locations', len(payload_moves), [eid for m in payload_moves for eid in m['event_ids']],
           'Paired exit and subsequent entry for the same physical payload instance at different locations. Initial population is excluded.',
           known=complete_evidence and not payload_gaps)
    metric('payload_unpaired_exits', 'Payload exits without a later entry', len(departures), [e['id'] for e in departures.values()],
           'Recorded payload exits with no subsequent entry for the same instance in this log. Select to inspect evidence gaps; these are not automatically payload losses.')
    metric('payload_tracking_conflicts', 'Payload tracking conflicts', len(payload_anomalies), [eid for a in payload_anomalies for eid in a['event_ids']],
           'Repeated exits before the next entry, or physical movement records missing an instance identifier/time. Select the contributing records to investigate; the reader does not repair them.')
    metric('journeys', 'Assigned AMR journeys', len(journeys), [eid for j in journeys.values() for eid in j['event_ids']],
           'Distinct assigned route plans. A multi-stop batch is one journey even when several task assignments are logged. This is not a completed-journey metric.',
           known=complete_evidence and all(e['journey_id'] for e in events if e['type'] in ASSIGNED))
    metric('lift_segments', 'Planned lift movements', len(lifts), [e['id'] for e in lifts],
           'Transfer and empty reposition segment records, each counted once regardless of carried task count. These are logged route-plan movements, not independent execution confirmations.')
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
            'software': metadata.get('software'), 'project_binding': metadata.get('project_binding'), 'findings': sorted(set(findings)),
            'tasks': tasks, 'events': events, 'metrics': metrics, 'payload_movements': payload_moves,
            'payload_tracking_findings': payload_anomalies,
            'journeys': list(journeys.values()), 'reconciliation': reconciliation,
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
